# Project Instructions for Claude

## Git and Version Control

- **NEVER create git commits** - Only the user creates commits
- **NEVER run git add, git commit, or git push commands**
- The user owns all files in this project and manages version control themselves

## Commit Messages

When the user is ready to commit, they will ask for a commit message suggestion.
- Provide a concise, single-line commit message when possible
- Follow the format: `<action>: <brief description>`
- Keep it under 72 characters if possible
- Be descriptive but concise

## Project Overview

This is PulseQ, an autonomous modular AI system that delivers daily personalized technology and AI news briefs. See README.md for project overview and general_instructions for full specifications.

## Session Resume

When resuming a conversation (e.g. after context compaction or a new session that references prior work):
- Orient yourself: read relevant files, check git status, review memory.
- Then **stop and wait** for the user to tell you what to do next.
- Never infer "the next step" from a summary and start implementing it. A summary describing pending work is not an instruction to do that work.
- User-invocable skills (`/spec_implement`, `/spec_review`, etc.) are only triggered by an explicit user invocation — never by session context.

## Execution Philosophy

- **Move fast** — prefer simple, working solutions over elaborate ones. Avoid over-engineering.
- **Zero backward compatibility concern** — never add migration shims, legacy fallbacks, or compatibility layers for old data or old behavior. Break things cleanly and move on.
- **Avoid one-way-door decisions** — a one-way-door decision is one that is costly or impossible to reverse and constrains the entire architecture (e.g. choosing a hosting platform, URL schema, database structure, framework). Only the user defines what counts as a one-way-door decision.
- **Flag before acting** — whenever a task requires a choice that could be a one-way-door, raise it in the "Questions for Clarification" section of the relevant spec rather than making the choice unilaterally. Do not implement until the user has answered.
- **Two-way doors are fine** — reversible decisions (file layout, variable names, minor UI choices) can be made independently without asking.

## Development Guidelines

**Testing Requirements:**
- Every code change MUST include corresponding unit tests
- Tests should cover new functionality, edge cases, and error conditions
- Code without tests is incomplete
- Python unit tests MUST reside in their own dedicated files under `tests/` (e.g. `tests/test_scout.py`), NOT inline within source files
- TypeScript/Next.js tests MUST reside under `__tests__/` or alongside components as `*.test.ts` / `*.test.tsx`
- After writing tests, ALWAYS run the appropriate coverage tool to verify coverage:
  - Python: `pytest --cov`
  - TypeScript: `jest --coverage` or `vitest run --coverage`
- All new code must be covered. Uncovered lines must be either tested or explicitly justified
- Prefer fewer, broader tests over many narrow ones. If a single test can assert multiple related behaviours without obscuring intent, merge them. Only use separate tests when the failure modes are meaningfully distinct and a combined test would hide which behaviour broke.
- Tests must be written alongside the code, not before it. Do not ask for approval before implementing.

**Test Assertion Quality:**
- **Each assertion should falsify exactly one thing.** Before writing an assertion, ask: what specific incorrect behaviour would this catch that no other assertion in this test already catches? If the answer is "nothing new", remove it.
- **Use named option objects instead of positional booleans in test helpers.** A boolean argument is opaque at the call site; a named property is self-documenting.
- **Assert on outcomes over implementation details.** If the observable result (return value, side effect, log message) fully proves the behaviour, prefer that over inspecting internal state. Only inspect internals when the result alone cannot distinguish correct from incorrect behaviour.

## Lambda Error Logging

- Every Lambda (Python or TypeScript) MUST log an error for every 4xx and 5xx response it returns.
- When a dependency failure is handled with fail-open behavior (e.g. continuing with a default value instead of raising), log a warning so the degraded state is visible.
- Unit tests MUST assert that the logger was called for each error path and each fail-open scenario (spy on `console.error`/`console.warn` in TS, `logger.error`/`logger.warning` in Python).

## Spec Compliance

- Code must faithfully implement the finalized spec — no undocumented additions or deviations.
- If coding reveals a new one-way-door decision, or requires an API/schema change not covered by the spec: stop, add a question to the spec, and wait for the user to answer before continuing.
- If a two-way-door improvement is spotted during coding, briefly propose it first — don't just do it.

## Specification Workflow

Specifications are developed iteratively through collaboration:

**Initial Draft:**
- Start each new spec with a "Questions for Clarification" section (2-5 key questions)
- Present the initial specification structure

**Iteration Cycle:**
- User provides feedback either:
  - By answering questions directly in the document
  - By adding comments in `<<...>>` format within the spec
- On each iteration:
  - When a user answers a question, incorporate the answer into the spec body and remove the question entirely
  - Remove the `<<...>>` markers once addressed
  - Remove the entire "Questions for Clarification" section once all questions are resolved
- Continue iterating until the spec is finalized

**Key Principle:** Each revision should cleanly incorporate feedback. Once a question is answered, the answer lives in the spec body — not in a Q&A section.

**Spec Length:**
- The body of a finalized spec (excluding "Commit Plan") must not exceed **200 lines** (soft limit). Prefer concise prose over verbose code snippets.

**Commit Plan:**
- Each finalized spec must include a "Commit Plan" section at the end with a **single commit** covering all changes.
- If the spec is large enough that a single commit feels unwieldy, that is a signal the spec should be broken into smaller specs — not that the commit plan should be split. Recommend this to the user instead of creating multiple commits.
- The commit must include its own tests — never commit code without the tests for that code.
- The commit entry should follow the format: `<action>: <brief description>` with a one-sentence explanation of what it contains.
