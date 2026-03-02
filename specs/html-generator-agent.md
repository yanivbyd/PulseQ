# Spec: HTML Generator Agent

## Overview

A local Python CLI script (`agents/writer.py`) that reads hard-coded input files, calls the OpenAI API, and writes an HTML file to `docs/` that references the shared stylesheet. The user updates input files manually, reviews the output, and commits and publishes the file themselves.

## Inputs

All file paths are hard-coded in the script. No CLI arguments.

| Input | Path | Purpose |
|---|---|---|
| Instructions | `inputs/instructions.md` | Content structure and style guidance; reused across runs |
| Stylesheet | `docs/style.css` | Shared CSS; provided to the AI so it uses correct class names |
| Topic | `inputs/topic.md` | Per-run content: article draft, brief, or bullet points |
| History | `inputs/history.md` | Past articles (ID + title + match description); read as context; updated manually |

## Behavior

1. Read all four input files from disk
2. Build prompt: instructions + stylesheet → system message; topic + history → user message
3. Call OpenAI Chat Completions (`gpt-4o`) and request an HTML document that links to `style.css` and overrides only `--accent` per-article
4. Write the response to `docs/<short-id>.html` (random 5-character alphanumeric ID)
5. Print the output path to stdout

The script does **not** commit, stage, push, or modify any input files — that is the user's responsibility.

## File Layout

```
writer/
  writer.py          ← the agent script
  requirements.txt   ← Python dependencies
  inputs/
    instructions.md  ← content/structure guide (committed, reused)
    topic.md         ← per-run content (committed, updated manually)
    history.md       ← content history log (committed, updated manually)
  tests/
    test_writer.py   ← unit tests
docs/
  style.css          ← shared stylesheet (committed, referenced by all articles)
  <short-id>.html    ← generated output (committed by user after review)
```

## Invocation

```bash
python writer/writer.py
# → writes docs/a3f9z.html and prints the path
```

The README will be updated with invocation instructions as part of the commit.

## API Key

Loaded from the `OPENAI_API_KEY` environment variable. The script fails fast with a clear error if the key is missing.

## Error Handling

- Missing or unreadable input files → print error and exit non-zero
- Missing API key → print error and exit non-zero
- OpenAI API error → print the error message and exit non-zero
- No retries — the user re-invokes on failure

## Testing

Tests live in `tests/test_writer.py` and mock the OpenAI client. Coverage targets:
- Happy path: valid inputs → correct file written with expected content
- Missing any input file → error exit
- Missing API key → error exit
- Auto-generated short ID is 5 alphanumeric characters and unique per run

## Commit Plan

- `refactor: extract shared stylesheet from x7k2q.html` — moves inline CSS to `docs/style.css`; updates `x7k2q.html` to reference it with a per-article `--accent` override
- `add: html-generator agent with tests` — adds `agents/writer.py`, `tests/test_writer.py`, `inputs/instructions.md`, `inputs/topic.md`, and `inputs/history.md`; updates `README.md` with invocation instructions
