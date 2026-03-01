# PulseQ

PulseQ is an autonomous, modular AI system that delivers a daily personalized technology and AI news brief — curated, written, and quizzed by agents.

## What It Does

Every day, PulseQ:

1. **Scouts** high-quality tech and AI news from curated sources
2. **Ranks** candidate stories based on your interests, novelty, and estimated impact
3. **Writes** a personalized ~1,000-word brief optimized for mobile reading
4. **Quizzes** you with 4 multiple-choice questions grounded in the brief
5. **Learns** from your answers and engagement to improve future briefs

## Agent Architecture

| Agent | Role |
|---|---|
| **Scout** | Fetches and normalizes articles from RSS feeds and APIs; deduplicates against history |
| **Ranker** | Scores candidate articles using user profile, novelty signals, and impact heuristics |
| **Writer** | Synthesizes the top stories into a concise, personalized daily brief |
| **Quizmaster** | Generates 4 MCQs strictly grounded in the brief content |
| **Coach** | Evaluates answers, captures feedback, and updates the user profile |

## Tech Stack

### Backend
- **Language**: Python (async)
- **AI Provider**: OpenAI API (GPT-4o)
- **Database**: AWS Aurora Serverless v2 (PostgreSQL)
- **Scheduler**: AWS EventBridge (daily cron)
- **Compute**: AWS Lambda / ECS

### Frontend
- **Framework**: Next.js (TypeScript)
- **Target**: Mobile-first PWA
- **Hosting**: AWS Amplify or S3 + CloudFront

### Infrastructure
- **Secrets**: AWS Secrets Manager (OpenAI API key, DB credentials)
- **Storage**: S3 (article blobs, optional)

## Design Principles

- **Autonomous** — runs daily on a schedule without manual prompting
- **Modular** — each agent is independently testable and replaceable
- **Observable** — deterministic, loggable, reproducible pipeline
- **Adaptive** — user profile evolves over time via simple, transparent heuristics
- **Extensible** — clean architecture ready for multi-agent decomposition

## Project Status

> Early development — architecture and scaffolding in progress.
