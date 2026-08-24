# DeltaGrid delivery roadmap

The machine-readable roadmap is [`DELIVERY_ROADMAP.json`](DELIVERY_ROADMAP.json). It is the current delivery plan, not an authority contract.

The roadmap is deliberately allowed to change. Dates, implementation choices, and lane ordering may move when better evidence appears. The fixed rules do not move with them: production stays on the last green `main`; security and authority failures block a merge; research failures are recorded rather than rescued by retuning; and UI or delivery work cannot create exchange, order, credential, or capital authority.

The current software-complete target is **2026-09-07**. That means a coherent research, shadow, and paper operating system with supported operator paths. It does not mean a profitable strategy has been proven or that capital must be activated by that date.

## Replanning

Each lane in the JSON file carries an exit condition and, where useful, alternative implementation options. Choose the shortest option that preserves the invariants. If a verified subsystem already solves a planned problem, integrate it. If a feature cannot name the release blocker it removes, defer it until after v1.

Targets more than 48 hours late trigger an explicit replan rather than silently sliding the whole schedule.
