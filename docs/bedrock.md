# Connecting Amazon Bedrock

Azathoth can run its models on [Amazon Bedrock](https://aws.amazon.com/bedrock/),
with the AWS credentials you already use, instead of or beside
[OpenRouter](openrouter.md). Your model traffic and spending then stay
inside your AWS account (ADR 0103).

This guide covers installing Bedrock support, giving Azathoth AWS
credentials, turning Bedrock on, pricing its models and authorizing them.
Each command is shown for the macOS Terminal and for Windows PowerShell.

Start with Azathoth installed and its venv active. See
[Installing Azathoth](install.md). How Azathoth chooses among the models you
authorize is the same for every provider; see
[How Azathoth Uses Models](openrouter.md#how-azathoth-uses-models).

## What You Need

- An AWS account, and a region where Bedrock offers the models you want.
- AWS credentials on this computer: a profile set up with `aws configure` or
  `aws sso login`, or the usual `AWS_*` variables. On AWS itself, such as on
  Fargate, the task's role is enough.
- Permission to list and call Bedrock models (see
  [The permissions it needs](#the-permissions-it-needs)).

## 1. Install Bedrock Support

Bedrock support is an optional extra. Install it into the same venv:

```bash
python -m pip install "azathoth-ai[bedrock]"
```

```powershell
python -m pip install "azathoth-ai[bedrock]"
```

The extra installs boto3, AWS's Python SDK. Until you turn Bedrock on, it is
never imported.

## 2. Give Azathoth AWS Credentials

Azathoth reads no AWS keys of its own. boto3 finds your credentials the way
the AWS CLI does: from the `AWS_*` variables, from a profile in `~/.aws`,
from SSO, or from the role of the task or instance it runs on.

If you use a named profile, select it for this terminal:

```bash
export AWS_PROFILE="<PROFILE>"
```

```powershell
$env:AWS_PROFILE = "<PROFILE>"
```

If you have the AWS CLI, check that the credentials work:

```bash
aws sts get-caller-identity
```

```powershell
aws sts get-caller-identity
```

### The permissions it needs

Azathoth lists the region's models and inference profiles, and calls models
through Bedrock's Converse API, which is authorized as `InvokeModel`. This
policy allows exactly that:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DiscoverModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:ListInferenceProfiles"
      ],
      "Resource": "*"
    },
    {
      "Sid": "InvokeModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:*:<ACCOUNT_ID>:inference-profile/*"
      ]
    }
  ]
}
```

The region in the foundation-model ARN is `*` because an inference profile,
such as `us.anthropic.…`, routes each call to the model in one of several
regions. Narrow either resource to the models you authorize, if you like.

### Anthropic models

Bedrock makes its serverless models available to every account, but
Anthropic's models need a one-time use-case form first. Submit it by opening
an Anthropic model in the Bedrock console's playground. Until then, calls to
those models fail with `AccessDeniedException`.

## 3. Turn Bedrock On

Turn Bedrock on, and name the region if your profile does not:

```bash
export AZATHOTH_BEDROCK=1
export AWS_REGION="us-east-1"
```

```powershell
$env:AZATHOTH_BEDROCK = "1"
$env:AWS_REGION = "us-east-1"
```

The region is `AWS_REGION`, then `AWS_DEFAULT_REGION`, then your profile's.
Azathoth uses one region per process; inference profiles reach the others.

OpenRouter stays on when `OPENROUTER_API_KEY` is set, so you may use both.
Their models never collide: Bedrock's are named `bedrock/<model id>`.

## 4. Price Your Models

Bedrock does not report its prices, so Azathoth cannot know what a call
costs unless you tell it. Write a pricing document, with the price per
million tokens of each model you use, from
[Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) for your
region:

```json
{
  "version": 1,
  "models": {
    "amazon.nova-pro-v1:0": {
      "input_usd_per_million_tokens": 0.8,
      "output_usd_per_million_tokens": 3.2
    }
  }
}
```

The figures are an example. Key each model by its Bedrock ID, without
`bedrock/`, and an inference profile by its profile ID. Then name the
document:

```bash
export AZATHOTH_BEDROCK_PRICING="$HOME/azathoth-work/bedrock-pricing.json"
```

```powershell
$env:AZATHOTH_BEDROCK_PRICING = "$HOME\azathoth-work\bedrock-pricing.json"
```

A model the document does not price has an unknown cost, never a zero one.
It still runs, and runs record their tokens. But a benchmark cannot score a
run that used it, and the optimizer never offers it as a cheaper model:

```text
Workflow step <STEP_ID> ran model bedrock/<MODEL_ID>, whose cost is unknown; price the model in AZATHOTH_BEDROCK_PRICING to score its run.
```

A priced model that your region does not offer is ignored, so one document
can serve several regions. When AWS changes a price, change the document.

## 5. Find and Authorize Models

List the models your region offers:

```bash
azathoth model list
```

```powershell
azathoth model list
```

```text
bedrock/<model id>  <Display Name>
```

The list holds every active text model that can be called on demand, by its
model ID, and every inference profile AWS defines, by its profile ID, such
as `us.anthropic.…` or `global.anthropic.…`. Some newer models can only be
called through a profile.

Look at one, then authorize it:

```bash
azathoth model show bedrock/<model id>
azathoth model authorize bedrock/<model id>
azathoth model portfolio
```

```powershell
azathoth model show bedrock/<model id>
azathoth model authorize bedrock/<model id>
azathoth model portfolio
```

`model show` reports the price from your pricing document, or `unknown`.
Bedrock does not report context windows, so they show as `unknown` too, and
a step that requires a minimum context window will not choose a Bedrock
model.

Everything else works as it does for OpenRouter, from judges to the
optimizer: see [Connecting OpenRouter](openrouter.md#4-authorize-models).

## In a Container

The container image includes Bedrock support. On Fargate, the task's role and
the region ECS sets are enough: pass only `AZATHOTH_BEDROCK` and the pricing
document. See [Running in a Container](container.md#bedrock).

## Child Workflows

A child workflow, run by the standard `run_workflow` or `loop_workflow`
tool, uses its parent's Bedrock configuration. The tools grant the child
`AZATHOTH_BEDROCK`, `AZATHOTH_BEDROCK_PRICING` and every `AWS_*` variable,
which includes any AWS credentials in the environment. A tool of your own that
runs `azathoth` grants them too.

## Troubleshooting

Each of these stops the command before it runs anything, with exit status 1.

**`boto3 is not installed`**: Bedrock is on, but the extra isn't installed in
this venv:

```text
AZATHOTH_BEDROCK is set, but boto3 is not installed; install azathoth-ai[bedrock].
```

Install it (step 1), or turn Bedrock off by unsetting `AZATHOTH_BEDROCK`.

**`no AWS region is configured`**: set `AWS_REGION` (step 3):

```text
AZATHOTH_BEDROCK is set, but no AWS region is configured; set AWS_REGION.
```

**`is not a valid Bedrock pricing document`**: the file named by
`AZATHOTH_BEDROCK_PRICING` can't be read, isn't JSON, or isn't shaped like
step 4's. The message ends with the first thing wrong, such as
`models.amazon.nova-pro-v1:0.output_usd_per_million_tokens: Field required`.

**`Bedrock model discovery request failed`**: Azathoth asked AWS for the
region's models and AWS refused. The message names AWS's error:
`NoCredentialsError` means boto3 found no credentials;
`UnrecognizedClientException` or `ExpiredTokenException` means they are
invalid or expired; `AccessDeniedException` means they lack
the permissions above.

**A step fails with `Bedrock request for model … failed`**: the call itself
was refused, for example `ThrottlingException` when you exceed your quota,
or `AccessDeniedException` for an Anthropic model before its use-case form.
The step's retry policy applies, as for any failed model call.

**A step fails with `Bedrock stopped model … without an answer`**, naming
`guardrail_intervened` or `content_filtered`: Bedrock blocked the reply.
Azathoth treats a blocked reply as a failed call, never as an answer.

## Next

- [Getting Started](getting-started.md) takes one workflow from import to
  production. Authorize Bedrock models where it authorizes OpenRouter's.
- [Running in a Container](container.md) runs the same commands in the image.
