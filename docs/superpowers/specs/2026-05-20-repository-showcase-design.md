# Repository Showcase Design

Date: 2026-05-20

## Goal

Prepare the project as a GitHub-ready research repository that can be shown to a technical reviewer, partner or future Codex session.

The repo should communicate:

- what the strategy hypothesis is;
- what the system currently does;
- what it intentionally does not do;
- how to run it;
- how to continue development safely with Codex;
- how Superpowers and Context7 fit into the workflow.

## Chosen Approach

Use a balanced presentation style:

- enough product/research context for non-developers;
- enough architecture/API detail for developers;
- explicit risk boundaries so the project is not mistaken for a live trading bot.

## Documentation Set

Top-level:

```text
README.md           main entrypoint
SPECIFICATION.md    formal project and strategy spec
PRESENTATION.md     concise show-and-tell brief
AGENTS.md           coding-agent instructions
```

Docs folder:

```text
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/GITHUB_SETUP.md
docs/CODEX_SUPERPOWERS_CONTEXT7.md
```

## Key Requirements

- Keep live trading disabled.
- State look-ahead/correlation risks clearly.
- Preserve existing code structure.
- Make GitHub setup copy-paste friendly.
- Document Superpowers and Context7 setup.
- Keep Codex instructions explicit and conservative.

## Out Of Scope

- Changing strategy implementation.
- Adding new backend features.
- Adding authentication.
- Adding screenshots or generated visual assets.
- Deploying to a remote VPS.

## Verification

After documentation changes:

- run tests;
- inspect git status;
- initialize a local Git repository if needed;
- create an initial commit if verification passes.
