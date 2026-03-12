# PulseQ Project Memory

## Architecture
- **writer pipeline**: Step Functions Express Workflow (WriterStateMachine) with 3 steps:
  - ArticleFunction (article_handler.py) — mandatory, raises on failure
  - QuizFunction (quiz_handler.py) — optional, Step Functions catches errors → NotificationState
  - NotificationFunction (notification_handler.py) — optional, warm-up is fail-open, IFTTT raises
- **infra/stack.py**: CDK stack — all AWS infra defined here
- **backend/index.ts**: Node.js Lambda — JSON API for frontend; uses SFNClient for /api/generate
- **mcp_server/server.py**: MCP server Lambda — uses _sfn_client to StartExecution
- **scout/**: Scout Lambda — finds topics, separate from writer pipeline

## Key Environment Variables
- `WRITER_STATE_MACHINE_ARN` — state machine ARN (replaces old WRITER_FUNCTION_ARN/WRITER_LAMBDA_NAME)
- `INPUT_BUCKET` — S3 bucket for instructions
- `ARTICLES_TABLE` / `TOPICS_TABLE` — DynamoDB table names
- `WEB_BASE_URL` — set on notification_fn (was on old writer_fn)

## Test Notes
- mcp_server tests fail in local env (pre-existing issue: boto3 not in global Python path)
- writer tests run with pytest from /writer directory, use Python 3.13 with boto3 available
- backend tests use Jest; @aws-sdk/client-sfn must be in package.json

## Patterns
- Python Lambda handlers: raise exceptions (Step Functions handles retry/catch)
- Python test pattern: patch boto3.client/resource, use _make_* helpers
- TypeScript: createHandler(ddbClient, lambdaClient, s3Client, sfnClient) factory pattern
