# multi-agent-swing-trader

A Claude Code agent team that builds, tests and honestly evaluates one
swing-trading hypothesis (H1, `docs/PREREGISTRATION.md`): buy liquid US stocks
that fell sharply on negative but non-fundamental news, sell two sessions
later. You talk to the **lead**; four teammates work in their own tmux panes.

| Agent | Model | Owns |
|---|---|---|
| lead (you talk here) | Opus | coordination, docs/STATUS.md |
| market-data | Sonnet | survivorship-free prices, universe, live price collector |
| news-intel | Sonnet | news ingestion, anonymized LLM labels, live news collector |
| quant | Opus | H1 rule, backtest, evaluation, trial ledger |
| auditor | Opus | independent red team: tries to break everything above |

## 1. One-time setup on the VM

```bash
git clone git@github.com:<you>/multi-agent-swing-trader.git && cd multi-agent-swing-trader
# copy this kit's files in, then:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install -y tmux                 # if missing
cp .env.example .env                     # add keys later; agents never read this file
make test-fast                           # expect "skipped": nothing is built yet
```

## 2. Review, then freeze (your checkpoint)

Read `contracts/`, `swing/config.py` and `docs/PREREGISTRATION.md`. Change
anything you disagree with now. Then lock it in:

```bash
git add -A && git commit -m "Base: contracts, config, agent team, frozen tests"
make freeze && git add FROZEN.sha256 && git commit -m "Freeze" && git tag -f frozen
make audit
```

## 3. Start the team

```bash
source .venv/bin/activate
./scripts/start-team.sh        # or: make team
```

This opens tmux session `swing`, starts the lead in pane 0, and the lead
reads `.claude/kickoff-prompt.md`, spawns the four teammates (each in its own
pane), builds the task list and starts work. Mouse mode is on: click a pane to
read or talk to that agent directly.

The first time, Claude Code asks you to trust the folder; accept it, or the
agent definitions and hooks won't load.

Useful tmux keys: `Ctrl+B` then `D` detaches (everything keeps running);
`./scripts/start-team.sh` again re-attaches. `Ctrl+B` then `Z` zooms a pane.

If split panes misbehave in VS Code's integrated terminal (Claude Code doesn't
support split-pane mode there), connect with plain `ssh` from a normal terminal
instead, or run `claude --teammate-mode in-process` and switch between
teammates with the arrow keys in the agent panel.

## 4. Working with it

- Talk only to the lead. Ask "status" any time.
- Permission prompts from teammates appear in the lead's pane. The allowlist in
  `.claude/settings.json` covers routine work, so prompts should be rare.
- The lead will stop and ask you for the decisions listed in `docs/ROADMAP.md`
  (data source, labeling budget, signing the pre-registration, the one trial).
- Phase 1 needs no API keys. Add `MASSIVE_API_KEY` before Phase 2 and
  `ANTHROPIC_API_KEY` before Phase 3.

## 5. Stopping and resuming

Tell the lead "shut down all teammates", wait, then `/exit`. To resume later:
`./scripts/start-team.sh`. Teammates don't survive a restart, so the lead
re-spawns them and briefs them from docs/STATUS.md, the git log and the tests.
If a stale session is in the way: `tmux kill-session -t swing`.

## Guard rails

- Frozen files (contracts, config, leakage tests, team setup) are protected by
  a PreToolUse hook, permission deny rules, `FROZEN.sha256` and `make audit`.
  Bash could still bypass the first two, so `make audit` plus git history is
  the real check. Run it whenever you look in.
- A teammate can't go idle while fast tests fail (TeammateIdle hook, at most
  two blocks in a row).
- Every backtest is logged append-only in `ledger/trials.jsonl`.
- Nothing can look at 2023 onward until you set `LOCKBOX_OPEN = True` yourself.

Agent teams are an experimental Claude Code feature; check
https://code.claude.com/docs/en/agent-teams if behaviour changes.
