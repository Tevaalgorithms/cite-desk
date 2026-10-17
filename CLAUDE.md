@AGENTS.md

# CLAUDE.md — Claude Code specifics

The shared project instructions are in `AGENTS.md` (imported above). Follow them in full.

## Working style in this repo

- Plan before large changes; implement **one roadmap ticket at a time** and say which ticket you are on.
- Prefer small, reviewable diffs on a feature branch. Do not push or open a PR unless asked.
- Run lint, type checks and tests for the area you changed before reporting done; report failures honestly with the output.
- When docs and code disagree, flag it and update the docs in the same change. Record deviations as ADRs in `docs/architecture/adrs.md`.
- Use the dedicated Read/Edit/Grep tools over shell equivalents where possible.

## Safety reminders

- Run a secret scan on `git diff --cached` before every commit (keys, tokens, private keys, `/Users/` paths, account ids).
- Do not claim a metric, price or license was verified unless it was.
