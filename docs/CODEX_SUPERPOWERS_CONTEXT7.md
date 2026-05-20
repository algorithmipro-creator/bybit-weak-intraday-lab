# Codex, Superpowers And Context7 Setup

This project is prepared for iterative development with Codex.

Recommended agent workflow:

```text
Codex + GitHub repo + Superpowers skills + Context7 MCP
```

## Current Local Status

On this machine:

- Superpowers skills are already installed under `~/.codex/superpowers`.
- Context7 MCP is configured in `~/.codex/config.toml`.
- Context7 was verified by resolving FastAPI documentation as `/fastapi/fastapi`.

This file documents how to reproduce the setup on another machine.

## Superpowers

Superpowers is a skill/workflow bundle for coding agents. It helps Codex move through:

```text
idea -> design -> spec -> implementation plan -> TDD -> verification -> review
```

### Install Superpowers For Codex

Ask Codex to follow the official installer:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/.codex/INSTALL.md
```

After installation, restart Codex so new skills are picked up.

Expected local skills include:

```text
using-superpowers
brainstorming
writing-plans
test-driven-development
systematic-debugging
verification-before-completion
requesting-code-review
receiving-code-review
```

## Context7 MCP

Context7 provides up-to-date library documentation through MCP. It is useful when Codex needs current docs for frameworks such as FastAPI, Streamlit, pandas, Plotly or Docker-related tooling.

### Example Codex MCP Config

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.context7]
command = "npx"
args = ["@upstash/context7-mcp@latest"]
```

Restart Codex after editing the config.

### Expected Use

When implementing framework-specific changes, Codex can use Context7 to resolve and query docs.

Example internal workflow:

```text
Resolve library: FastAPI -> /fastapi/fastapi
Query docs: request validation, background jobs, TestClient, dependencies
```

## Recommended Project Prompt

For future Codex tasks:

```text
Read README.md, SPECIFICATION.md, PRESENTATION.md, AGENTS.md and .codex/project_brief.md.
Use Superpowers workflow.
Use Context7 for current framework documentation when changing FastAPI, Streamlit, pandas or Plotly code.
Keep live trading disabled unless explicitly requested as a separate reviewed task.
Run tests before reporting completion.
```

## First Useful Codex Tasks

### 1. Causal Signal Mode

```text
Add a causal/live-scan-safe signal mode.
It must calculate features using only data available at signal time.
Keep the existing historical scanner for research labeling.
Add tests proving no future data is used.
```

### 2. TP/SL Optimizer

```text
Add a TP/SL grid optimizer endpoint and Streamlit page.
Use existing trade simulation logic.
Add tests for optimizer aggregation.
```

### 3. Backend Safety

```text
Add strict job_id validation, date-range limits, max concurrent scan limits and API tests.
Keep the default deployment private/research-oriented.
```

## Repository Agent Instructions

The main repository-level instructions live in:

```text
AGENTS.md
.codex/project_brief.md
```

Codex should read both before making changes.
