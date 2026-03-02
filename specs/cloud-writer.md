# Spec: Cloud Writer

## Overview

Move the Writer agent from a local CLI script to a serverless cloud function (AWS Lambda) that can be triggered on demand or on a schedule. The Writer logic is unchanged; only the execution environment, input source, and output destination change.

## Compute

AWS Lambda (Python 3.12 runtime). The existing `writer.py` `run()` function becomes the Lambda handler with a thin adapter wrapper. No container needed at this stage.

## Inputs

Input files are read from S3 at runtime:

| File | S3 key | Change frequency |
|---|---|---|
| `instructions.md` | `pulseq-inputs/instructions.md` | Rare |
| `topic.md` | `pulseq-inputs/topic.md` | Each run |
| `history.md` | `pulseq-inputs/history.md` | Each run |

The user uploads updated input files to S3 before triggering a run (same mental model as editing local files before running the script).

## Output

HTML written to S3 at `pulseq-output/<short-id>.html`. The bucket has static website hosting enabled (public read). The Lambda response body contains:

```json
{ "url": "http://pulseq-output.s3-website-<region>.amazonaws.com/<short-id>.html" }
```

No CloudFront or additional hosting required at this stage.

## Trigger

Manual HTTP endpoint via API Gateway → Lambda. On-demand only; no scheduled trigger.

## Secrets

`OPENAI_API_KEY` stored in AWS Secrets Manager; Lambda reads it via the AWS SDK at cold start. No env-var injection needed.

## Error Handling

Same policy as the local script: fail fast, log to CloudWatch. No retries.

## What Changes vs. Local

| Concern | Local | Cloud |
|---|---|---|
| Execution | `python writer/writer.py` | API Gateway → Lambda (on-demand) |
| Input files | Local disk (`writer/inputs/`) | S3 bucket |
| Output | `docs/<id>.html` on disk | S3 static website; URL returned in HTTP response |
| API key | `.env` file | AWS Secrets Manager |
| Logs | Terminal stdout | CloudWatch Logs |

## What Does NOT Change

- `writer.py` core logic (`run()` function) — no rewrite needed
- Prompt construction
- OpenAI API call
- Short-ID generation
- Error handling behavior

## File Layout

```
writer/
  writer.py           ← unchanged core logic
  lambda_handler.py   ← thin adapter: reads S3, calls run(), writes output
  requirements.txt    ← add boto3
infra/
  lambda.tf (or cdk)  ← Lambda + API Gateway + IAM + Secrets Manager
```

## Commit Plan

- `add: S3 input/output adapter for writer Lambda` — adds `writer/lambda_handler.py` and updates `requirements.txt`; unit-tests the adapter with mocked S3 and Secrets Manager
- `add: Lambda infra (Terraform/CDK)` — provisions Lambda, API Gateway, S3 input + output buckets (output with static website hosting), IAM role, and Secrets Manager secret; no application logic changes
