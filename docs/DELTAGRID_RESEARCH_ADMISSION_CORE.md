# DeltaGrid Research Admission Core

## Purpose

Mission 94 introduces a local, deterministic admission boundary for future
research requests. The package can decide whether a request passes its declared
contract, dataset, budget, and non-alpha-control gates. Its decision is the
terminal output: it does not run the admitted work.

## Authority boundary

The controlling contract is
`contracts/DELTAGRID_RESEARCH_ADMISSION_CORE_V1.json`. It authorizes only the
admission-core implementation and validation with synthetic fixtures. Research
remains frozen. Market data, real-market backtests, development evaluation,
validation, holdout, model training, paper or live trading, exchange access,
capital deployment, autonomous research, and autonomous promotion remain
unauthorized.

## Package architecture

The six-file package under `offchain/research/admission/` separates immutable
models and hashing, metadata-only dataset resolution, the SQLite trial ledger,
the fixed control registry, and the admission service. New production code uses
only the Python standard library.

## Dataset resolver

`DatasetResolver` accepts a catalog that the caller already loaded and verifies
its canonical identity. It rejects duplicate or unknown dataset IDs, hash
mismatches, unknown or unauthorized classes, validation and holdout splits,
protected records, unsafe artifact paths, and authorization-stage mismatches.
It returns hashed metadata only and never opens the referenced artifact.

Mission 94 admits only `SYNTHETIC_FIXTURE` records with the
`SYNTHETIC_DEVELOPMENT` split. A filename never grants permission.

## Trial ledger

`TrialLedger` stores immutable budgets and reservations plus append-only trial
events in caller-supplied local SQLite files. Foreign keys, uniqueness
constraints, checks, and database triggers enforce the fixed budget definition,
unique trial and request identities, unique declared trial numbers, and the
update/delete prohibition.

Reservation uses `BEGIN IMMEDIATE`. Every successful reservation consumes one
budget slot regardless of later status. This ensures that two separate
connections contending for the final slot can produce at most one successful
reservation.

Status transitions are explicit. Terminal statuses cannot transition back to a
non-terminal status, and no reset or erase API exists.

## Control registry

`ControlRegistry` exposes exactly four immutable specifications:
`NO_TRADE_CONTROL`, `BUY_AND_HOLD_CONTROL`, `SEEDED_RANDOM_CONTROL`, and
`SIMULATOR_STATE_MACHINE_CONTROL`. All are non-alpha and execution is
unauthorized. Validation is exact and fail closed; the registry neither imports
nor executes strategy or simulator code and has no runtime registration method.

## Preflight

`ResearchAdmissionService.preflight()` performs structural, contract,
repository, budget, dataset, split, and control checks. It produces a
deterministically hashed `PRECHECK_PASS` or `PRECHECK_STOP` decision, writes
nothing to the ledger, reserves no trial, and executes nothing.

## Admission

`ResearchAdmissionService.admit()` checks the minimum envelope needed to find
the controlling budget, then atomically reserves the declared trial before
substantive dataset and control gates. A passing request records `ADMITTED`. A
post-reservation gate failure records `STOPPED`, and the reserved attempt still
counts against the budget.

## Reason tokens

Machine reason tokens are fixed by the contract and include repository,
contract, budget, reservation, dataset, protected-data, validation, holdout,
control-parameter, request-integrity, and internal-integrity failures. Human
text may explain a token but never replaces it.

## No-execution boundary

The package does not open dataset artifacts, load candles, trades, or order
books, generate signals, calculate returns, P&L, fees, costs, or risk, place or
simulate orders, rank trials, select candidates, train models, contact an
exchange, or invoke a strategy, simulator, engine, or network library.

## Next possible interface mission

After successful implementation, the named possible next action is
`AUTHORIZE_RESULT_BUNDLE_AND_ENGINE_SERVICE_CONTRACT`. This name does not
authorize that contract or any result-bundle, engine-service, research, or
execution implementation now.
