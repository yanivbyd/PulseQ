#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Running Python tests"
"$REPO_ROOT/.venv/bin/pytest" "$REPO_ROOT/writer/tests/" --cov=writer --cov-report=term-missing

echo "==> Running Node.js tests"
(cd "$REPO_ROOT/web_server" && npm test)

echo "==> All tests passed — deploying"
(cd "$REPO_ROOT/infra" && source .venv/bin/activate && cdk deploy --require-approval never)
