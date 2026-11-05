# Running Azathoth on AWS

Azathoth runs on AWS as a fleet of queue workers (ADR 0107, ADR 0109).
Programs send job requests to an Amazon SQS queue; workers on AWS Fargate
run them against one PostgreSQL database and send each result to a second
queue. One CloudFormation template,
[`deploy/aws/azathoth.yaml`](../deploy/aws/azathoth.yaml), creates:

- the job queue, its dead-letter queue and the result queue;
- a private bucket that keeps every input given by reference;
- the Fargate service of workers, which scales on the queue's backlog;
- the IAM roles, with exactly the permissions the workers use.

It takes your network, your database and, optionally, a bucket inputs may
come from and a bucket the S3 tools may work in. It creates no database.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged. Each step's commands set
variables the later steps use, so run them in one terminal.

## What You Need

- An AWS account, and the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
  version 2, signed in with permission to create the stack's resources.
- A VPC with subnets for the workers. Private subnets need a NAT gateway to
  reach the image's registry and the model providers; public subnets work
  with `AssignPublicIp=ENABLED`.
- A PostgreSQL database, version 15 or later, that those subnets reach, such
  as an Amazon RDS instance, with an empty database the workers may create
  tables in.
- Azathoth on your own machine (see [Installing Azathoth](install.md)), with
  the `postgres` extra, and a way to reach the database from it, to import
  and promote workflows.
- An OpenRouter API key, or Bedrock access (see
  [Connecting Amazon Bedrock](bedrock.md)), for workflows that use models.
  The example in this guide uses none.
- A checkout of this repository, for the template and the example files.

## 1. Store the Secrets

The database's URL and the OpenRouter key are kept in AWS Secrets Manager,
and ECS hands them to the workers; they never appear in the stack or the
task definition:

```bash
DATABASE_SECRET=$(aws secretsmanager create-secret --name azathoth/database --secret-string "postgresql://azathoth:<PASSWORD>@<HOST>:5432/azathoth" --query ARN --output text)
OPENROUTER_SECRET=$(aws secretsmanager create-secret --name azathoth/openrouter --secret-string "<OPENROUTER_API_KEY>" --query ARN --output text)
```

```powershell
$DATABASE_SECRET = aws secretsmanager create-secret --name azathoth/database --secret-string "postgresql://azathoth:<PASSWORD>@<HOST>:5432/azathoth" --query ARN --output text
$OPENROUTER_SECRET = aws secretsmanager create-secret --name azathoth/openrouter --secret-string "<OPENROUTER_API_KEY>" --query ARN --output text
```

Skip the OpenRouter secret if the workers use no OpenRouter model, and
leave `OpenRouterSecretArn` out in step 2.

## 2. Deploy the Stack

Name your VPC and the workers' subnets, then deploy from the checkout:

```bash
STACK=azathoth
VPC=vpc-0123456789abcdef0
SUBNETS=subnet-0123456789abcdef0,subnet-0fedcba9876543210
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET
```

```powershell
$STACK = "azathoth"
$VPC = "vpc-0123456789abcdef0"
$SUBNETS = "subnet-0123456789abcdef0,subnet-0fedcba9876543210"
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET
```

Every other parameter has a default:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `AssignPublicIp` | `DISABLED` | `ENABLED` for public subnets without a NAT gateway. |
| `ImageUri` | `ghcr.io/eldritchinc/azathoth:1.2.0` | The image; pin it by digest, or use your own ECR copy (see [Copying the Image Into ECR](#copying-the-image-into-ecr)). |
| `CpuArchitecture` | `X86_64` | Or `ARM64`, which costs less; the image is built for both. |
| `TaskCpu`, `TaskMemory` | `1024`, `2048` | One task's CPU units and MiB. |
| `EnableBedrock` | `false` | `true` grants the Bedrock calls and turns Bedrock on in the stack's region. |
| `InputBucket`, `InputPrefix` | none | Where `s3://` inputs may come from (step 8). |
| `DataBucket`, `DataPrefix` | none | Where the S3 tools may read and write (step 8). |
| `MaxReceiveCount` | `5` | Receipts before the dead-letter queue takes a message. |
| `MinTasks`, `MaxTasks` | `1`, `4` | The fewest and most workers. |
| `ScaleOutBacklog` | `10` | Waiting messages that add a worker. |

The stack sets no Bedrock pricing document, so Bedrock models have unknown
costs on it.

Read the stack's outputs into variables for the steps that follow:

```bash
output() { aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
JOB_QUEUE=$(output JobQueueUrl)
RESULT_QUEUE=$(output ResultQueueUrl)
CLUSTER=$(output ClusterName)
TASK_DEFINITION=$(output TaskDefinitionArn)
WORKERS=$(output SecurityGroupId)
LOGS=$(output LogGroupName)
```

```powershell
function output($key) { aws cloudformation describe-stacks --stack-name $STACK --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue" --output text }
$JOB_QUEUE = output JobQueueUrl
$RESULT_QUEUE = output ResultQueueUrl
$CLUSTER = output ClusterName
$TASK_DEFINITION = output TaskDefinitionArn
$WORKERS = output SecurityGroupId
$LOGS = output LogGroupName
```

## 3. Let the Workers Reach the Database

The workers' security group accepts no connections; the database's must
accept theirs. Name the database's security group:

```bash
DATABASE_GROUP=sg-0123456789abcdef0
aws ec2 authorize-security-group-ingress --group-id $DATABASE_GROUP --protocol tcp --port 5432 --source-group $WORKERS
```

```powershell
$DATABASE_GROUP = "sg-0123456789abcdef0"
aws ec2 authorize-security-group-ingress --group-id $DATABASE_GROUP --protocol tcp --port 5432 --source-group $WORKERS
```

## 4. Initialize the Database

`azathoth init` creates the tables and installs the standard tools. Run it
once, as a one-off task from the workers' own task definition, with its
command overridden by
[`deploy/aws/init-overrides.json`](../deploy/aws/init-overrides.json):

```bash
NETWORK="awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$WORKERS],assignPublicIp=DISABLED}"
aws ecs run-task --cluster $CLUSTER --task-definition $TASK_DEFINITION --launch-type FARGATE --network-configuration $NETWORK --overrides file://deploy/aws/init-overrides.json
```

```powershell
$NETWORK = "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$WORKERS],assignPublicIp=DISABLED}"
aws ecs run-task --cluster $CLUSTER --task-definition $TASK_DEFINITION --launch-type FARGATE --network-configuration $NETWORK --overrides file://deploy/aws/init-overrides.json
```

With public subnets, say `assignPublicIp=ENABLED`. Its output goes to the
workers' log group (step 7). Until it has run, every worker that takes a
message stops, saying what to do:

```text
Database postgresql://azathoth@<HOST>:5432/azathoth is not initialized; run azathoth init.
```

The message stays on the queue, and the next worker takes it once the
database is ready. Run `init` again after every upgrade.

## 5. Deploy a Workflow

Workflows are imported and promoted from any machine that reaches the
database, such as your own over a VPN or an SSH tunnel. Point Azathoth at it,
and deploy the word count from the
[Examples Tour](examples.md#1-word-count-tools-without-models), which needs
no model:

```bash
export AZATHOTH_DATABASE="postgresql://azathoth:<PASSWORD>@<HOST>:5432/azathoth"
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow promote a1000000-0000-4000-8000-000000000001
```

```powershell
$env:AZATHOTH_DATABASE = "postgresql://azathoth:<PASSWORD>@<HOST>:5432/azathoth"
azathoth tool import examples/tools/word-count.json
azathoth tool import examples/tools/word-count-process.json
azathoth workflow import examples/workflows/redundant-word-count.json
azathoth workflow promote a1000000-0000-4000-8000-000000000001
```

The workers use what was promoted from then on, with no restart.

## 6. Send a Job

A job is one message whose body is a job request (ADR 0097), such as
[`deploy/aws/example-request.json`](../deploy/aws/example-request.json):

```json
{
  "kind": "invoke",
  "version": 1,
  "idempotency_key": "aws-guide-1",
  "workflow_id": "a1000000-0000-4000-8000-000000000001",
  "input": {"value": "the old ones wait"}
}
```

Send it:

```bash
aws sqs send-message --queue-url $JOB_QUEUE --message-body file://deploy/aws/example-request.json
```

```powershell
aws sqs send-message --queue-url $JOB_QUEUE --message-body file://deploy/aws/example-request.json
```

Sending it again with the same key runs nothing; it replays the first result.
Use a new key for a new job.

## 7. Read the Result

Every final result arrives on the result queue, as the line `azathoth job
run` prints:

```bash
aws sqs receive-message --queue-url $RESULT_QUEUE --wait-time-seconds 20 --query "Messages[0].Body" --output text
```

```powershell
aws sqs receive-message --queue-url $RESULT_QUEUE --wait-time-seconds 20 --query "Messages[0].Body" --output text
```

```json
{"kind": "invoke", "version": 1, "idempotency_key": "aws-guide-1", "status": "succeeded", "replayed": false, "invocation_id": "<INVOCATION_ID>", "result": {"result": 4}, "error": null}
```

The request's key is also the message's `idempotency_key` attribute.
Delete a result once your program has it, with `aws sqs delete-message` and
the message's receipt handle. Each worker writes one line per message to the
log group:

```bash
aws logs tail $LOGS --follow
```

```powershell
aws logs tail $LOGS --follow
```

## 8. Inputs From S3

A request may name its input in S3 instead of carrying it, when the stack
allows where it lies. Redeploy with the bucket, and a prefix to allow one
folder of it:

```bash
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET InputBucket=azathoth-inputs InputPrefix=requests/
```

```powershell
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET InputBucket=azathoth-inputs InputPrefix=requests/
```

A request's input is then `{"uri": "s3://azathoth-inputs/requests/<KEY>",
"media_type": "text/markdown"}`, read before its run starts, at most 10 MiB,
and kept in the stack's content bucket by its digest (ADR 0108).

### Data Larger Than the Cap

Data larger than an input may be stays in S3, and a workflow works with it
there (ADR 0110): `split_s3_object` streams one object into chunk objects,
`map_workflow` runs a child over the chunks, and each child reads its own
with `read_s3_object`. The tools use the task role, so give it a bucket and
a prefix to work under. Redeploy with them:

```bash
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET DataBucket=azathoth-data DataPrefix=work/
```

```powershell
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET DataBucket=azathoth-data DataPrefix=work/
```

A deploy keeps the value of every parameter it is not given, so the input
bucket of step 8 stays as it was. The role may then get and put
objects under `s3://azathoth-data/work/`, and nothing else in the bucket;
it may not list it, so S3 answers a missing object with `403` rather than
`404`.

The [large-file example](../examples/large-file/README.md) counts the words
of a text file of any size this way, in chunks of whole lines of at most
1 MiB. Upload a file, then deploy the example from the machine that reaches
the database:

```bash
aws s3 cp book.txt s3://azathoth-data/work/inbox/book.txt
azathoth tool import examples/large-file/tools/sum-results.json
azathoth workflow import examples/large-file/workflows/count-words-in-chunk.json
azathoth workflow import examples/large-file/workflows/count-words-in-large-file.json
azathoth workflow promote a1000000-0000-4000-8000-000000000008
azathoth workflow promote a1000000-0000-4000-8000-000000000009
```

```powershell
aws s3 cp book.txt s3://azathoth-data/work/inbox/book.txt
azathoth tool import examples/large-file/tools/sum-results.json
azathoth workflow import examples/large-file/workflows/count-words-in-chunk.json
azathoth workflow import examples/large-file/workflows/count-words-in-large-file.json
azathoth workflow promote a1000000-0000-4000-8000-000000000008
azathoth workflow promote a1000000-0000-4000-8000-000000000009
```

Step 5 imported `word_count_process`, which each child uses. Send the
example's request, whose input is only the file's URI, and read its result
as in step 7:

```bash
aws sqs send-message --queue-url $JOB_QUEUE --message-body file://examples/large-file/request.json
```

```powershell
aws sqs send-message --queue-url $JOB_QUEUE --message-body file://examples/large-file/request.json
```

```json
{"kind": "invoke", "version": 1, "idempotency_key": "large-file-1", "status": "succeeded", "replayed": false, "invocation_id": "<INVOCATION_ID>", "result": {"result": <WORDS>}, "error": null}
```

`result` holds the file's word count. The chunks stay under
`s3://azathoth-data/work/chunks/`, one folder per step attempt, as the
evidence of what each child read; nothing deletes them, so expire them with
an S3 lifecycle rule on that prefix. The children of a map run in the same
task as their parent, four at a time here, so a large file is counted by one
worker; more jobs, not more chunks, are what add workers.

## 9. Scaling and Stopping

The service runs `MinTasks` workers, adds one while `ScaleOutBacklog`
messages wait, and removes one once nothing has waited or run for five
minutes, never fewer than `MinTasks` or more than `MaxTasks`. Change the
bounds by redeploying with new values.

A worker that is scaled in, replaced by a deploy, or stopped by ECS for any
reason drains: it hands its running job back to the queue, and another
worker resumes it from its journal (ADR 0105). One that dies outright leaves
its message to come back within two minutes, and it is resumed the same
way.

## 10. Messages That Keep Failing

A message that stops `MaxReceiveCount` workers in a row is moved to the
dead-letter queue, rather than received forever. Read one:

```bash
DEAD_LETTERS=$(output DeadLetterQueueUrl)
aws sqs receive-message --queue-url $DEAD_LETTERS --query "Messages[0].Body" --output text
```

```powershell
$DEAD_LETTERS = output DeadLetterQueueUrl
aws sqs receive-message --queue-url $DEAD_LETTERS --query "Messages[0].Body" --output text
```

Once its cause is fixed, move every message back to the job queue:

```bash
aws sqs start-message-move-task --source-arn $(aws sqs get-queue-attributes --queue-url $DEAD_LETTERS --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
```

```powershell
aws sqs start-message-move-task --source-arn (aws sqs get-queue-attributes --queue-url $DEAD_LETTERS --attribute-names QueueArn --query "Attributes.QueueArn" --output text)
```

A request that does not decode never gets there: it is rejected, sent to the
result queue and deleted the first time.

## 11. Upgrading

Redeploy with the new image, pinned by its digest, which
`docker buildx imagetools inspect` prints, then run `init` once more, as in
step 4:

```bash
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET ImageUri=ghcr.io/eldritchinc/azathoth:<VERSION>@sha256:<DIGEST>
aws ecs run-task --cluster $CLUSTER --task-definition $(output TaskDefinitionArn) --launch-type FARGATE --network-configuration $NETWORK --overrides file://deploy/aws/init-overrides.json
```

```powershell
aws cloudformation deploy --stack-name $STACK --template-file deploy/aws/azathoth.yaml --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DatabaseSecretArn=$DATABASE_SECRET OpenRouterSecretArn=$OPENROUTER_SECRET ImageUri=ghcr.io/eldritchinc/azathoth:<VERSION>@sha256:<DIGEST>
aws ecs run-task --cluster $CLUSTER --task-definition (output TaskDefinitionArn) --launch-type FARGATE --network-configuration $NETWORK --overrides file://deploy/aws/init-overrides.json
```

ECS replaces the workers one by one; each one replaced drains first. A deploy
whose workers fail their health check is rolled back by itself.
[Verifying the Image](container.md#verifying-the-image) checks a new image's
signature before you deploy it.

## Copying the Image Into ECR

Workers in private subnets with no route to the internet pull from your own
Amazon ECR instead. Copy the image there, both architectures at once:

```bash
REGISTRY=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
aws ecr create-repository --repository-name azathoth
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
docker buildx imagetools create --tag $REGISTRY/azathoth:1.2.0 ghcr.io/eldritchinc/azathoth:1.2.0
```

```powershell
$REGISTRY = "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com"
aws ecr create-repository --repository-name azathoth
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
docker buildx imagetools create --tag $REGISTRY/azathoth:1.2.0 ghcr.io/eldritchinc/azathoth:1.2.0
```

Then deploy with `ImageUri=$REGISTRY/azathoth:1.2.0`. The subnets still need
routes to SQS, S3, Secrets Manager, CloudWatch Logs and ECR, through VPC
endpoints, and to the model providers.

## Tearing Down

Delete the stack. The content bucket is kept, because it is the evidence of
what every run was given; empty and remove it yourself once you no longer
need it:

```bash
BUCKET=$(output ContentBucketName)
aws cloudformation delete-stack --stack-name $STACK
aws s3 rb s3://$BUCKET --force
```

```powershell
$BUCKET = output ContentBucketName
aws cloudformation delete-stack --stack-name $STACK
aws s3 rb s3://$BUCKET --force
```

The secrets, the database and its security group rule are yours to remove
too.

## Troubleshooting

**Tasks stop with `CannotPullContainerError`**: the subnets have no route to
`ghcr.io`. Add a NAT gateway, use public subnets with
`AssignPublicIp=ENABLED`, or copy the image into ECR.

**Tasks stop with `ResourceInitializationError` naming a secret**: the
secret's ARN is wrong, or the subnets cannot reach Secrets Manager.

**Every worker stops with `is not initialized; run azathoth init`**: run
step 4.

**Workers start, then are replaced again and again**: their health check
fails. The log group shows why; a worker that cannot reach SQS stops at its
first receive.

**A job's result says `invalid_input` for an `s3://` input**: the object is
outside `InputBucket` and `InputPrefix`, or missing. The result's message
says which.

**A job fails with `split_s3_object could not read` or `read_s3_object could
not read` and `403`**: the object is outside `DataBucket` and `DataPrefix`,
or missing; the task role may not list the bucket, so S3 says `403` for
both.
