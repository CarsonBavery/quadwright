# Setup

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Python | 3.11+ (3.12 recommended) | Everything |
| Git | any recent | Version control, pre-commit |
| Node.js | 18+ | Optional: ccusage, Ponytail and Context7 later |
| VS Code + Claude Code extension | latest | Daily development |

## 1. Run the setup script

From the repo root:

- macOS / Linux: `./scripts/setup.sh` (add `--ml` to also install ML packages)
- Windows PowerShell: `.\scripts\setup.ps1` (add `-Ml` for ML packages)

If PowerShell blocks the script, run this once in the same window first:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

The script creates `.venv`, installs Quadwright with dev tools, initializes
git, installs the pre-commit hooks, and runs lint, tests, and config validation.

In VS Code, pick the interpreter in `.venv` when prompted
(Command Palette > "Python: Select Interpreter").

## 2. Put it on GitHub (Week 1, Day 1)

```bash
git add .
git commit -m "chore: project scaffold (M0)"
git remote add origin https://github.com/YOUR-USERNAME/quadwright.git
git push -u origin main
```

Then replace `YOUR-USERNAME` in the README badge. CI runs on every push.

## 3. Claude Code plugins: install-now stack

Type these inside a Claude Code session (VS Code panel or `claude` in a terminal):

```text
/plugin install pyright-lsp@claude-plugins-official
/plugin install commit-commands@claude-plugins-official
/plugin install learning-output-style@claude-plugins-official
```

Then run `/reload-plugins`. `pyright-lsp` needs `pyright-langserver` on your
PATH; the setup script installs it into `.venv`, so open VS Code with the
venv active (or activate it before running `claude`).

If a marketplace is reported missing, run
`/plugin marketplace add anthropics/claude-plugins-official` and retry.

## 4. Measure token usage (baseline first)

```bash
npx ccusage@latest daily      # tokens and cost per day
npx ccusage@latest session    # per conversation
```

Record one week of daily numbers before adding anything from the
"test later" list, so every tool is judged against a baseline.

## 5. Test later (weeks 4-5), one at a time, measured

```text
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
/ponytail lite
```

```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp
```

```text
/plugin install pr-review-toolkit@claude-plugins-official
```

Only install Ponytail from `DietrichGebert/ponytail`; many copies exist.
Plugins run with your user privileges, so stick to sources you trust.
