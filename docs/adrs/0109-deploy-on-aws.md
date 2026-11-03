# ADR 0109: Deploy on AWS

- Status: Accepted
- Date: 2026-11-02
- Decided in: #127

## Context

Azathoth 1.1 runs on AWS: programs send job requests to a queue, and
workers from one image run them against one PostgreSQL database
(ADR 0101, ADR 0102, ADR 0107), reading inputs from S3 (ADR 0108). Every
piece existed, and each left part of its deployment to this decision:

- how a deployment gets the image, and whether the image is pinned, attested
  and signed (ADR 0101);
- where the database's URL is kept, and whether workers authenticate to RDS
  with IAM (ADR 0102);
- the queues, the dead-letter queue, IAM and ECS (ADR 0107).

An operator should get from an empty account to a job's result without
designing any of that, and a security review should be able to read exactly
what the workers may do.

## Decision

### One CloudFormation template

[`deploy/aws/azathoth.yaml`](../../deploy/aws/azathoth.yaml) is the whole
deployment: one stack, deployed with the AWS CLI alone. CloudFormation is
AWS's own, needs no toolchain beyond the CLI, and is reviewable as one file;
teams on Terraform translate it. Every intrinsic is written in its long form,
so the template is plain YAML that the tests read.

### What it creates, and what it takes

It creates:

- the job queue, with a two-minute visibility timeout and 20-second polls to
  match the worker, and a dead-letter queue that takes a message after
  `MaxReceiveCount` receipts, 5 by default;
- the result queue;
- a private, encrypted content bucket for resolved inputs (ADR 0108), kept
  when the stack is deleted, since it is the evidence of what each run was
  given;
- the cluster, the log group, a security group that accepts no connections,
  the task definition and the Fargate service;
- the execution and task roles;
- scaling on the queue.

It takes the VPC and subnets, the image, the database URL's secret, an
optional OpenRouter key's secret, an optional input bucket and prefix, and
the scaling bounds. It creates no database: sizing, backups and networking
are each team's own, and the guide shows the one rule the workers need.

### Least privilege

The task role grants exactly the calls the worker makes: receiving,
deleting and hiding messages on the job queue, sending to the result
queue, reading and writing under the content bucket's `evidence/` prefix,
reading under the input prefix when there is one, and Bedrock's discovery
and invocation, the same actions as the Bedrock guide, only when Bedrock is
on. No grant names every action, and only model discovery names every
resource. The execution role reads only the secrets it injects.

The worker is allowed exactly the input locations its role may read:
`--allow-input-bucket` and the IAM grant come from the same two
parameters.

### Secrets

The database URL and the OpenRouter key live in AWS Secrets Manager, and
ECS injects them as `AZATHOTH_DATABASE` and `OPENROUTER_API_KEY`. Neither
appears in the template, the task definition or the environment.

IAM authentication to RDS is deferred. It needs a token generated for each
connection inside `PostgresDatabase`, which a secret holding the URL does
not.

### The task

The task runs the worker on a read-only root filesystem. Fargate has no
tmpfs, so an ephemeral volume at `/tmp` holds the tools' scripts and the
heartbeat (ADR 0101). The container's health check is
`azathoth worker health`, every 30 seconds, with three retries and a minute
to start; its stop timeout is 60 seconds, longer than a drain takes
(ADR 0107). A deployment whose workers fail their health check is rolled
back by ECS's circuit breaker.

### Scaling

The service runs between `MinTasks` and `MaxTasks` workers, 1 and 4 by
default. It adds one when `ScaleOutBacklog` messages wait, 10 by default,
and removes one after five minutes with nothing waiting and nothing being
run. A running job's message is hidden, so counting only waiting messages
would stop busy workers. A worker scaled in drains, and hands its job to
another.

### `init` is the operator's

`azathoth init` runs as a one-off task from the workers' own task
definition, with its command overridden, once after the first deploy and
once after each upgrade. The stack never runs it: a schema change is a
deliberate step. Until it has run, a worker stops at its first message,
saying so.

### The image

The template takes the image's URI, by default
`ghcr.io/eldritchinc/azathoth:1.1.0`, and the guide pins it by digest. Workers
with a route to the internet pull from GitHub's registry. Those without one
pull a copy in the operator's own ECR, made with one
`docker buildx imagetools create`, which copies both architectures. ECR's
pull-through cache for GitHub's registry needs a stored GitHub credential
even for a public image, so it is not the default.

### The supply chain

Both stages of the `Dockerfile` start from the same base, pinned by digest,
so a rebuild of a release uses exactly the base it was tested with.
Dependabot proposes each new digest of the base's tag as a pull request,
tested like any other change.

The release attaches an SBOM and full provenance to the image, and signs
the pushed image by its digest with cosign, keylessly, through the release
workflow's GitHub identity. Anyone can check that an image is the one the
workflow built for its tag:

```text
cosign verify ghcr.io/eldritchinc/azathoth:<VERSION> --certificate-identity https://github.com/EldritchInc/azathoth/.github/workflows/release.yml@refs/tags/v<VERSION> --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

### Bedrock

`EnableBedrock` grants the Bedrock calls and turns Bedrock on in the stack's
region. Bedrock reports no prices, and its pricing document is a file the
task cannot be given without baking it into an image, so Bedrock models on
the stack have unknown costs (ADR 0103).

### Verified, and where it is not

The tests read the template and resolve it as a stack would for each
combination of its optional parameters. They check its commands against
Azathoth's own parser, its grants, its secrets and its scaling. The guide
is checked against the template, and the result it shows is the result its
job really has, run locally. The `Dockerfile` and the release workflow are
checked for the pin, the attestations and the signature.

Nothing in the repository reaches AWS. A release that changes the template,
the worker or the image is deployed once to a sandbox account first, and
must return the guide's result and survive a worker stopped mid-job. That
deployment is the first place the worker meets real SQS and S3, and it is a
release gate.

## Consequences

### Positive

- One command deploys a fleet of workers with least-privilege IAM, and a
  reviewer reads every permission in one file.
- No secret appears in the template, the task definition or the logs.
- A worker replaced for any reason costs no finished work, and a broken
  deploy rolls itself back.
- An image can be verified as the release workflow's, down to its base's
  digest and its packages.

### Negative

- CloudFormation only; Terraform and CDK users translate it.
- No database is created, so a first deployment needs one made by hand.
- Workflows are imported and promoted from a machine that reaches the
  database, which in private subnets means a VPN, a tunnel or a bastion.
- Bedrock models on the stack have unknown costs until the pricing document
  can come from somewhere a task reaches.
- A digest-pinned base must be updated deliberately; Dependabot proposes the
  updates, but someone merges them.
- The template's first real test is the sandbox deployment; no check in the
  repository catches what only CloudFormation would refuse.

## Alternatives Considered

### CDK

Rejected. It needs Node and a build, and the deployment becomes a program to
maintain rather than a document to read.

### Terraform

Rejected as the shipped form. It is common, but not AWS's own, and one
template should be the reference. A translation can follow.

### Create the database in the stack

Rejected. A database outlives a stack, and its size, engine version,
backups and network are decisions each team makes for itself.

### IAM authentication to RDS now

Deferred. It needs Azathoth to make a token for every connection, while a
secret holding the URL needs nothing from it.

### Scale on waiting messages alone

Rejected. A running job's message is hidden, so scale-in would stop workers
mid-job; they would hand their jobs back, safely but for nothing.

### Run `init` on every task start

Rejected. Every worker would race to migrate, and a schema change would
happen whenever a task started rather than when an operator chose.

### ECR's pull-through cache by default

Rejected. It needs a GitHub credential stored in Secrets Manager even to
pull a public image; a one-time copy needs none.

### Pin the base through a build argument

Rejected. Dependabot updates digests it finds in `FROM` lines, and could not
be relied on to follow a build argument.
