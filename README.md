# PulseQ

PulseQ is an autonomous, modular AI system that delivers a daily personalized technology and AI news brief — curated, written, and quizzed by agents.

## Writer Agent

The Writer agent runs as an AWS Lambda. It reads input files from S3, calls GPT-4o, and writes a styled HTML article to the public `pulseq` S3 bucket.

### Trigger

```bash
curl -X POST <api-gateway-url>/run
# → {"url": "http://pulseq.s3-website.eu-west-1.amazonaws.com/<id>.html"}
```

### Input files

Stored in S3 under `s3://pulseq-inputs/inputs/`. The `s3/pulseq-inputs/` directory in this repo mirrors that bucket — edit files there and upload before triggering a run.

| File | Purpose |
|---|---|
| `inputs/instructions.md` | Visual style and content guidance |
| `inputs/topic.md` | Per-run article content — edit this each time |
| `inputs/history.md` | Past articles log — update manually after each run |

### S3 sync

```bash
# Push local changes to S3
bash s3/upload.sh

# Pull S3 state back to local (e.g. after a run produces new output)
bash s3/download.sh
```

`upload.sh` syncs both `s3/pulseq-inputs/` → `s3://pulseq-inputs/` and `s3/pulseq/` → `s3://pulseq/`.
`download.sh` does the reverse.

### Typical workflow

1. Edit `s3/pulseq-inputs/inputs/topic.md` with the new article topic
2. Run `bash s3/upload.sh` to push inputs to S3
3. Trigger the Lambda: `curl -X POST <api-gateway-url>/run`
4. Open the returned URL to review the article
5. Run `bash s3/download.sh` to pull the generated HTML into `s3/pulseq/`
6. Update `s3/pulseq-inputs/inputs/history.md` with the new article title, then upload again

### Shared stylesheet

`s3/pulseq/style.css` is the shared stylesheet referenced by all generated pages. It lives in the `pulseq` bucket alongside the HTML files.

## Infrastructure

CDK stack is in `infra/`. It provisions the two S3 buckets, Secrets Manager secret, Lambda, and API Gateway.

### Deploy

```bash
cd infra
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk synth          # smoke-test — prints CloudFormation template, no AWS changes
cdk deploy         # creates all resources in eu-west-1
```

### After first deploy

Set the OpenAI API key in Secrets Manager (only needed once):

```bash
aws secretsmanager put-secret-value \
  --secret-id pulseq/openai-api-key \
  --secret-string "sk-..." \
  --region eu-west-1
```

Upload input files to S3:

```bash
bash s3/upload.sh
```

## Running Tests

```bash
.venv/bin/pytest writer/tests/ --cov=writer --cov-report=term-missing
```

## Tech Stack

- **Language**: Python
- **AI Provider**: OpenAI API (GPT-4o)
- **Compute**: AWS Lambda (Python 3.12)
- **IaC**: AWS CDK (Python), region `eu-west-1`
- **Secrets**: AWS Secrets Manager (`pulseq/openai-api-key`)
- **Storage**: S3 — `pulseq-inputs` (inputs), `pulseq` (generated HTML, public website)

## Roadmap

The full PulseQ pipeline will:

1. **Scout** high-quality tech and AI news from curated sources
2. **Rank** candidate stories based on your interests, novelty, and estimated impact
3. **Write** a personalized ~1,000-word brief optimized for mobile reading
4. **Quiz** you with 4 multiple-choice questions grounded in the brief
5. **Learn** from your answers and engagement to improve future briefs
