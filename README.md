# PulseQ

PulseQ is an autonomous, modular AI system that delivers a daily personalized technology and AI news brief — curated, written, and quizzed by agents.

## Writer Agent

The Writer agent runs as an AWS Lambda. It reads input files from S3, calls GPT-4o, stores the article in DynamoDB, and sends an iOS push notification with the article URL.

### Trigger

```bash
curl -X POST https://3mlilr6w93.execute-api.eu-west-1.amazonaws.com/run
# → {"url": "https://<cloudfront-domain>/<article-id>"}
```

### Input files

Stored in S3 under `s3://pulseq-inputs/inputs/`. The `s3/pulseq-inputs/` directory in this repo mirrors that bucket — edit files there and upload before triggering a run.

| File | Purpose |
|---|---|
| `inputs/instructions.md` | Visual style and content guidance |
| `inputs/topics.json` | Pool of topics — one is picked at random each run |
| `inputs/history.md` | Past articles log — update manually after each run |

### S3 sync

```bash
# Push local changes to S3
bash s3/upload.sh

# Pull S3 state back to local
bash s3/download.sh
```

### Typical workflow

1. Edit `s3/pulseq-inputs/inputs/topics.json` to add or update topics
2. Run `bash s3/upload.sh` to push inputs to S3
3. Trigger the Lambda: `curl -X POST <writer-api-url>/run`
4. Open the returned URL to review the article
5. Update `s3/pulseq-inputs/inputs/history.md` with the new article title, then upload again

## Frontend

A React SPA (Vite + React Router) served from S3 via CloudFront.

- **Home** (`/`): lists recent articles as accent-coloured cards
- **Article** (`/:id`): renders the article

### Local development

```bash
cd frontend
npm install

# Create a .env file (already committed as .env — edit if needed):
# VITE_USER_ID=user1
# VITE_API_PROXY_TARGET=https://dvfy0u2uikiwg.cloudfront.net

npm run dev   # → http://localhost:5173
```

The Vite dev server proxies `/api/*` to the deployed CloudFront/Lambda so the UI is fully functional locally.

## Backend

A Node.js 22.x Lambda serving a JSON API for articles.

| Endpoint | Description |
|---|---|
| `GET /api/article-summaries?userId=<id>` | List of article metadata (no HTML) |
| `GET /api/article/:articleId` | Full article including generated HTML |

CloudFront routes `/api/*` to this Lambda and `/*` to the S3-hosted React SPA.

## Infrastructure

CDK stack is in `infra/`. It provisions S3 buckets, DynamoDB, Secrets Manager secrets, writer Lambda, backend Lambda, two API Gateways, and a unified CloudFront distribution.

### Deploy

```bash
cd infra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk synth          # smoke-test — prints CloudFormation template, no AWS changes
cdk deploy         # creates all resources in eu-west-1
```

The full deploy script (tests → CDK → frontend build → S3 sync → CloudFront invalidation):

```bash
bash deploy.sh
```

### After first deploy

Set secrets in Secrets Manager (only needed once):

```bash
aws secretsmanager put-secret-value \
  --secret-id pulseq/openai-api-key \
  --secret-string "sk-..." \
  --region eu-west-1

aws secretsmanager put-secret-value \
  --secret-id pulseq/ifttt-key \
  --secret-string "your-ifttt-webhook-key" \
  --region eu-west-1
```

Upload input files to S3:

```bash
bash s3/upload.sh
```

## Running Tests

```bash
# Python (writer Lambda)
.venv/bin/pytest writer/tests/ --cov=writer --cov-report=term-missing

# Backend (Node.js JSON API) — install deps once: npm install
cd backend && npm test

# Frontend (React SPA) — install deps once: npm install
cd frontend && npm test
```

## Tech Stack

- **Languages**: Python (writer Lambda), TypeScript / Node.js 22.x (backend Lambda), TypeScript + React (frontend)
- **AI Provider**: OpenAI API (GPT-4o)
- **Frontend**: Vite + React Router, CSS Modules
- **Compute**: AWS Lambda — Python 3.12 (writer), Node.js 22.x (backend)
- **Hosting**: CloudFront — unified distribution for SPA (`/*`) and JSON API (`/api/*`)
- **Storage**: DynamoDB (`pulseq-articles`), S3 (`pulseq-inputs`, `pulseq-frontend`)
- **IaC**: AWS CDK (Python), region `eu-west-1`
- **Secrets**: AWS Secrets Manager (`pulseq/openai-api-key`, `pulseq/ifttt-key`)
- **Notifications**: IFTTT Webhooks → IFTTT iPhone app

## iOS Push Notifications

When a new article is generated, the Lambda calls an IFTTT webhook which pushes a notification to your iPhone. Tapping it opens the article directly in Safari.

**Setup (one-time)**

1. Install the **IFTTT** app on your iPhone and allow notifications
2. At ifttt.com, create an applet:
   - **If:** Webhooks → "Receive a web request" → event name: `PulseQ`
   - **Then:** Notifications → "Send a rich notification from the IFTTT app"
     - Title: `PulseQ`
     - Message: `{{Value2}}`
     - Link URL: `{{Value1}}`
3. Get your webhook key from ifttt.com/maker_webhooks → Documentation
4. Store it in Secrets Manager (see Infrastructure → After first deploy)

---

## Roadmap

The full PulseQ pipeline will:

1. **Scout** high-quality tech and AI news from curated sources
2. **Rank** candidate stories based on your interests, novelty, and estimated impact
3. **Write** a personalized ~1,000-word brief optimized for mobile reading
4. **Quiz** you with 4 multiple-choice questions grounded in the brief
5. **Learn** from your answers and engagement to improve future briefs
