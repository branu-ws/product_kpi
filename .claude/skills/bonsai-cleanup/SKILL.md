---
name: bonsai-cleanup
description: Use after a substantial coding session (new feature, large refactor, or 300+ changed lines / 5+ files) to prune dead code, integrate new logic with existing patterns, align public interfaces, sync docs, and enforce lint/type/test gates before calling the work done.
---

# Bonsai Cleanup

Post-development pass: prune, shape, align, document, verify. Run stages in order — each depends on the previous leaving a clean tree.

## 1. Prune
- Remove dead code, unused imports, and deprecated/superseded code paths.
- Delete tests, mocks, and fixtures tied to what you just removed.
- Sanity-check the tree still imports/compiles before moving on.

## 2. Shape
- Fold new code into existing conventions: logging, error handling, shared utilities.
- Collapse duplicated/copy-pasted logic introduced during development.
- Look beyond the diff: scan the whole repo for the same pattern/duplication so the refactor is applied consistently everywhere, not just in the files just touched.

## 3. Align interfaces
- Verify every public entry point (CLI commands, API routes, MCP tools/resources/prompts — whichever this repo exposes) still matches its latest implementation.
- Update schemas/docs for any added, renamed, or removed arguments and endpoints.
- Skip this stage if the repo has no external-facing interface.

## 4. Document
- Update README.md so setup, dependencies, and architecture stay accurate.
- Update any interface-facing docs (API reference, MCP prompt guides) touched in stage 3.

## Quality gates
Run the project's actual configured commands (don't assume — check pyproject.toml/package.json first), typically:
- `ruff check . && ruff format --check .`
- `mypy .`
- `pytest` (only if tests exist)

All must exit 0 with zero warnings. On failure, read the error, fix it, and re-run — don't skip a gate to "finish."
