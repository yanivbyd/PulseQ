#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Running Python tests"
"$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/writer/tests/" "$REPO_ROOT/scout/tests/" --cov=writer --cov=scout --cov-report=term-missing

echo "==> Running backend tests"
(cd "$REPO_ROOT/backend" && npm test)

echo "==> Running frontend tests"
(cd "$REPO_ROOT/frontend" && npm test)

echo "==> Uploading inputs to S3"
aws s3 sync "$REPO_ROOT/s3/pulseq-inputs/" s3://pulseq-inputs/ --region eu-west-1

echo "==> Deploying infrastructure"
(cd "$REPO_ROOT/infra" && source .venv/bin/activate && cdk deploy --require-approval never)

echo "==> Building and deploying frontend"
(cd "$REPO_ROOT/frontend" && VITE_USER_ID=user1 npm run build)
FRONTEND_URL=$(aws cloudformation describe-stacks --stack-name WriterStack \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text)
aws s3 sync "$REPO_ROOT/frontend/dist/" s3://pulseq-frontend/ --delete --region eu-west-1
DIST_DOMAIN=$(echo "$FRONTEND_URL" | sed 's|https://||')
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?DomainName=='$DIST_DOMAIN'].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*"
