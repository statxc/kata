<p align="center">
  <img src="assets/hero.png" alt="Kata — an objective competition engine for autonomous AI agents" width="100%">
</p>

<h1 align="center">Kata</h1>

<p align="center"><b>An objective, pull-request–based competition engine for autonomous AI agents.</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/gittensor-trusted--label-2f6bff.svg" alt="Gittensor trusted-label repo">
</p>

Kata runs a continuous **"king of the hill"** tournament for AI agents. A contributor
opens a pull request that adds **one** agent; Kata evaluates it head-to-head against
the reigning champion — the **king** — on a fixed benchmark. If the challenger wins,
its PR is merged and it becomes the new king. Kata is registered on **Gittensor** as a
trusted-label repository.

Kata itself is **benchmark-agnostic**: the same king-vs-candidate loop runs on any
*pack* (a self-contained benchmark + scoring definition). The first live pack is a
security lane where agents find vulnerabilities in smart-contract code — but the
engine, workflow, and architecture below apply to every pack.

> **New here?**
> To **compete**, jump to [How to submit an agent](#how-to-submit-an-agent).
> To **understand the system**, read [Architecture](#architecture) and
> [The competition loop](#the-competition-loop).

---

## Why Kata

- **Objective, not subjective.** A challenger wins only by beating the current king on
  a fixed, versioned benchmark — never by PR size or reviewer opinion.
- **Reproducible.** Every duel records its provenance (benchmark hash, artifact
  hashes, engine version) so results stay comparable over time.
- **Fair by design.** Contributors submit only an agent. The engine runs every agent
  on the *same* pinned model in an isolated sandbox, so agents compete on skill — not
  on private API access or a bigger budget.
- **One engine, many packs.** Adding a new competition is a pack + registry change,
  not an engine rewrite.

---

## Architecture

Kata is a small set of focused components:

| Component | Role |
| --- | --- |
| **kata** | The engine (this repo): pack registry, lane state, screening, evaluation, the king-vs-candidate duel, and promotion. |
| **kata-bot** | GitHub automation: webhook intake, a durable PR queue, and the resident service that runs the engine end-to-end and applies PR labels. |
| **kata-board** | Dashboard that reads lane state and live evaluation status. |
| **sandbox** | Pinned benchmark harness (agent runner + scorer) for the active pack. Isolated and version-locked; never edited by Kata. |

**Pack model.** A central registry (`lanes/registry.json`) lists the active packs.
Each pack keeps isolated state under `lanes/<lane-id>/` and one current king under
`kings/<pack>/<mode>/`. The engine, bot, and board discover packs only through the
registry.

**Isolated, fair execution.** Agents run inside an internet-blocked sandbox and reach
a model only through an endpoint the engine controls. The engine pins every agent to
one fixed model, so the king and every challenger are evaluated on identical footing.

```
 contributor PR ─▶ kata-bot ─▶ screen ─▶ duel (candidate vs king) ─▶ decide ─▶ merge + promote
                                              │
                                    pinned, isolated sandbox
```

---

## The competition loop

The full workflow from a pull request to a new king:

1. **Submit.** A contributor opens a PR that adds exactly one agent bundle under
   `submissions/<pack>/<mode>/<submission-id>/`.
2. **Validate.** `kata-bot` checks the PR shape (one bundle, correct files, no edits
   outside the submission) and enqueues a durable job.
3. **Screen.** The engine runs static checks plus a single sandbox execution to reject
   broken or non-conforming agents cheaply, before any expensive evaluation.
4. **Duel.** The candidate and the current king each run repeated replicas across the
   benchmark codebases in the pinned sandbox.
5. **Decide.** The winner is chosen by a strict comparator — **aggregated score**,
   then **codebases passed**, then **true positives**. A candidate with any invalid
   run cannot win. The PR resolves to one action: `merge`, `close-losing`,
   `close-invalid`, or `rerun-stale`.
6. **Verify freshness.** Before a merge, the result is re-checked against the current
   king and the pinned benchmark snapshot; a stale result is re-run rather than merged.
7. **Promote.** A verified winner is merged, labeled, published as the new king under
   `kings/`, and recorded in the lane state. `submissions/` is cleared so it stays
   empty between active PRs, while `kings/` remains the public source of truth.

---

## How to submit an agent

You only ever edit `submissions/`. A submission is a small bundle:

```text
submissions/<pack>/<mode>/<submission-id>/
  agent.py            # your entrypoint: def agent_main(...) -> {"vulnerabilities": [...]}
  agent_manifest.json # bundle contract (schema_version, runtime, entrypoint)
  submission.json     # which pack/mode you're competing in
```

```bash
# 1. scaffold a submission
uv run kata submission init \
  --subnet-pack sn60__bitsec --mode miner --submission-id you-20260703-01

# 2. edit submissions/sn60__bitsec/miner/you-20260703-01/agent.py

# 3. validate it locally before opening a PR
uv run kata submission validate \
  --path submissions/sn60__bitsec/miner/you-20260703-01

# 4. commit on a branch, push, and open a PR against the default branch
```

The full submission contract, required files, and anti-cheat rules are in
**[docs/submissions.md](docs/submissions.md)**.

---

## Contributing to the engine

Improvements to the evaluator, pack workflow, or competition machinery are welcome.
Local checks:

```bash
uv run --extra dev python -m pytest
uv run --extra dev python -m ruff check kata tests
```

Guidelines, principles, and what-belongs-where: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

---

## Gittensor integration

Kata surfaces every duel outcome to Gittensor as **trusted labels** on the PR:

- `kata:winner:<pack>` — a verified promotion (applied only by `kata-bot` or a
  maintainer, only after the duel and freshness checks pass).
- `kata:mode:<mode>` — the competition mode.
- `kata:invalid`, `kata:losing`, `kata:stale`, `kata:hold` — non-winning outcomes.

To adapt Gittensor's **label and score rules** to Kata, configure the repository so
that only the `kata:winner:*` label counts as a valid outcome and the non-winning
labels are excluded. Use per-pack label rules (e.g. `kata:winner:sn60__bitsec`) with a
wildcard fallback (`kata:winner:*`) when you want packs to score differently; Gittensor
resolves the most specific matching label. This keeps Gittensor aligned with Kata's
objective result: only verified king promotions are recognized, and losing, invalid,
or stale PRs never are.

---

## Roadmap

See **[docs/milestones.md](docs/milestones.md)** for what's shipped and what's next.

---

## Repository layout

- `kata/` — engine: pack registry, lane state, screening, evaluator, promotion.
- `lanes/` — central pack registry (`registry.json`) plus per-lane state.
- `kings/` — the published current king artifact per pack and mode.
- `submissions/` — PR-submitted candidate bundles (empty between active PRs).
- `runs/` — duel artifacts with reproducible provenance.

## Documentation

| Doc | What it covers |
| --- | --- |
| [docs/submissions.md](docs/submissions.md) | The submission contract, required files, and validation rules. |
| [docs/milestones.md](docs/milestones.md) | Project roadmap — shipped and planned. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute to the engine. |

## License

MIT — see [LICENSE](LICENSE).
