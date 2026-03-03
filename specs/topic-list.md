# Spec: Topic List Input

## Questions for Clarification

1. **File format** — Should the new file be `topics.json` (replacing `topic.md`) or keep the `.md` extension with JSON content inside it?

Answer: topics.json

2. **History interaction** — After a topic is selected, should the selected topic be appended to `history.md` automatically, or does the user manage history manually as today?

Answer: Still manual

3. **Empty/missing topics list** — If the JSON file has an empty array or is missing, should Lambda fail fast (error 500) or fall back to a default behaviour?

Answer: Fast fail

4. **Topic removal after selection** — Should the selected topic be removed from the list in S3 after a run (so each topic is used only once), or is the list reused across runs (random pick each time)?

Answer: Don't remove it, generating an article doesn't mean the user has read it

## Overview

Replace the single-topic `topic.md` input with a `topics.json` file containing a list of topic objects. On each Lambda invocation, the handler picks one topic at random, constructs a topic string, and passes it directly to `writer.run()`. History is not passed to the writer (reserved for the scout agent). All other logic (S3 output, IFTTT notification) is unchanged.

## Input File Changes

### topics.json

`s3://pulseq-inputs/inputs/topics.json` replaces `s3://pulseq-inputs/inputs/topic.md`.

Each topic is an object with `title`, `description`, and an optional `format` field (reserved for future use):

```json
{
  "topics": [
    {
      "title": "N+1 Query Problem at Scale",
      "description": "Detection patterns, batching strategies."
    },
    {
      "title": "WebAssembly beyond the browser",
      "description": "Use cases and runtimes.",
      "format": "explainer"
    }
  ]
}
```

The handler constructs a plain-text string `"{title} — {description}"` from the chosen entry and passes it to `run()`.

### history.json

`s3://pulseq-inputs/inputs/history.json` replaces `s3://pulseq-inputs/inputs/history.md`. History is **not** read by the writer Lambda; it is kept in S3 for future use by the scout agent.

## Lambda Changes

In `_download_inputs` (renamed to `_load_inputs`):

1. Download `instructions.md` and `topics.json` (no longer `topic.md`; history not downloaded).
2. Parse `topics.json`; raise `ValueError` if the `topics` array is empty or missing.
3. Pick one topic at random (`random.choice`); construct topic string `"{title} — {description}"`.
4. Return `topic_str` to the handler.

The handler passes the topic string directly to `run(topic=...)`.

## Writer Changes

`writer.py` `run()` signature changes to accept `topic: str` as an explicit parameter instead of reading it from a file. History is removed entirely from the writer prompt.

```python
def run(base_dir: Path, docs_dir: Path, topic: str) -> None:
```

`instructions.md` is still read from disk.

## S3 Inputs Summary

| File | S3 key | Change |
|---|---|---|
| `instructions.md` | `pulseq-inputs/inputs/instructions.md` | Unchanged |
| `topics.json` | `pulseq-inputs/inputs/topics.json` | **New** (replaces `topic.md`) |
| `history.json` | `pulseq-inputs/inputs/history.json` | **New** (replaces `history.md`; for scout only) |

## Commit Plan

- `refactor: replace topic/history markdown inputs with JSON and random topic selection` — updates `writer.py` `run()` signature to accept `topic` and `history` as parameters; updates `lambda_handler.py` to read `topics.json` and `history.json`, pick a random topic, and serialise history; updates all unit tests; updates local sample inputs under `s3/pulseq-inputs/inputs/`
