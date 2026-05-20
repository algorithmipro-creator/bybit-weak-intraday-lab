# GitHub Setup

This guide turns the project folder into a GitHub repository.

## 1. Check Project Root

Run commands from the folder that contains `README.md`, `SPECIFICATION.md`, `docker-compose.yml` and `bybit_weak_intraday/`.

```bash
pwd
ls
```

On Windows PowerShell:

```powershell
Get-Location
Get-ChildItem
```

## 2. Initialize Git

```bash
git init
git add .
git commit -m "initial bybit weak intraday lab"
git branch -M main
```

## 3. Create GitHub Repository

Create an empty repository on GitHub, for example:

```text
bybit-weak-intraday-lab
```

Do not add a GitHub README during creation if this local repository already has one.

## 4. Push

SSH:

```bash
git remote add origin git@github.com:YOUR_USER/bybit-weak-intraday-lab.git
git push -u origin main
```

HTTPS:

```bash
git remote add origin https://github.com/YOUR_USER/bybit-weak-intraday-lab.git
git push -u origin main
```

## 5. Connect To Codex

In ChatGPT/Codex:

1. Open settings.
2. Connect GitHub.
3. Grant access to the new repository.
4. Start a Codex task from the repository.

Suggested first prompt:

```text
Read README.md, SPECIFICATION.md, AGENTS.md and .codex/project_brief.md.
Run the tests.
Then add a causal/live-scan-safe signal mode that does not use future day data.
Keep live trading disabled.
Add tests for the new causal calculations.
```

## 6. Recommended Branch Workflow

```bash
git checkout -b feature/causal-signal-mode
```

After changes:

```bash
python -m pytest -q
git status
git add .
git commit -m "add causal signal mode"
git push -u origin feature/causal-signal-mode
```

Open a pull request into `main`.

## 7. Files That Should Not Be Committed

The repository intentionally ignores:

```text
.env
.venv/
data/bybit_archive_cache/
data/jobs/*
*.log
```

Keep secrets and large downloaded archive files out of Git.
