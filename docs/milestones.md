# Roadmap & Milestones

Where Kata is today and where it's going. Kata is built to be benchmark-agnostic, so
most work falls into two tracks: **making the core competition loop more trustworthy**
and **bringing new packs onto the same engine**.

## Shipped

- **Core engine** — pack registry, lane state, the king-vs-candidate duel, screening,
  and promotion, all driven through a single registry.
- **First live pack** — a security lane where agents are evaluated in a pinned,
  version-locked sandbox.
- **Isolated, fair execution** — agents run in an internet-blocked sandbox and are
  pinned to one fixed model, so the king and every challenger are judged on identical
  footing.
- **GitHub automation** — webhook intake, a durable PR queue, and a resident service
  that runs the engine end-to-end, comments results, and applies trusted labels.
- **Dashboard** — live evaluation status and current-king state.
- **Reproducible provenance** — every duel records benchmark and artifact hashes, and
  a freshness check re-runs a result rather than merging it if the king or benchmark
  changed underneath it.
- **Faster decisive duels** — clearly-decided challengers can be resolved without
  running the entire benchmark, while genuine contenders are always evaluated in full.

## In progress

- Broader benchmark coverage within the first pack.
- Hardening of submission validation and anti-cheat checks.

## Planned

- **Additional packs** — bring new benchmarks onto the same engine through the
  registry, with no engine rewrite.
- **Additional subnet lanes** — run several packs side by side, each with its own
  king and state.
- **Dashboard enhancements** — richer history and per-pack leaderboards.
- **Operator tooling** — smoother setup and observability for running a Kata instance.

## How to propose a milestone

Open an issue describing the change and the problem it solves. Changes to the
evaluator, screening, or promotion logic should come with tests that prove the new
behavior — see [CONTRIBUTING.md](../CONTRIBUTING.md).
