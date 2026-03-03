#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Running Python tests"
"$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/writer/tests/" --cov=writer --cov-report=term-missing

echo "==> Running Node.js tests"
(cd "$REPO_ROOT/web_server" && npm test)

echo "==> All tests passed — deploying"
(cd "$REPO_ROOT/infra" && source .venv/bin/activate && cdk deploy --require-approval never)

echo "==> Syncing style.css to S3"
aws s3 cp "$REPO_ROOT/s3/pulseq/style.css" s3://pulseq/style.css

echo "==> Invalidating CloudFront cache"
CSS_URL=$(aws cloudformation describe-stacks --stack-name WriterStack \
  --query "Stacks[0].Outputs[?OutputKey=='CssUrl'].OutputValue" --output text)
DIST_DOMAIN=$(echo "$CSS_URL" | sed 's|https://||' | cut -d'/' -f1)
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?DomainName=='$DIST_DOMAIN'].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/style.css"
