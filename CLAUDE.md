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

## Development Guidelines

**Testing Requirements:**
- Development follows **TDD**: write the failing tests first, get user approval, then implement
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
  - When a user answers a question, add the answer as a section below the question — do NOT delete the question yet
  - Remove the `<<...>>` markers once addressed
  - Remove the "Questions for Clarification" section (questions and answers) only once the spec is finalized
- Continue iterating until the spec is finalized

**Key Principle:** Each revision should cleanly incorporate feedback. Questions remain visible alongside their answers until the spec is finalized.

**Spec Length:**
- The body of a finalized spec (excluding "Questions for Clarification" and "Commit Plan" sections) must not exceed **200 lines** (soft limit). Prefer concise prose over verbose code snippets.

**Commit Plan:**
- Each finalized spec must include a "Commit Plan" section at the end
- Split along meaningful boundaries (e.g. database schema before agent logic, shared utilities before dependents). Avoid micro-commits for trivial changes; avoid bundling unrelated work into one giant commit
- Each commit must include its own tests — never commit code without the tests for that code
- Each commit entry should follow the format: `<action>: <brief description>` with a one-sentence explanation of what it contains
