# ADR-0042: One-Command Mission Pack Runner

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

## Status

Accepted

## Context

Mission 41 added a local mission automation harness for verification.

DeltaGrid still requires too much manual copy-paste to create future missions.

The project needs a safe local mission pack runner that can apply generated mission packs from one command.

## Decision

Add a one-command mission pack runner.

Files:

- scripts/mission_pack_runner.py
- offchain/tests/test_mission_pack_runner.py

Code commit:

- 66898c0 Add one-command mission pack runner

The runner supports JSON mission packs with:

- code files
- docs files
- overwrite mode
- append-once mode
- verification plans
- code commit paths
- docs commit paths
- optional code commit
- optional docs commit
- optional push
- dry-run mode

The runner performs:

- safe path validation
- forbidden content scanning
- clean-start checks
- file generation
- verification execution
- log creation
- JSON summary generation

## Safety

The mission pack runner is development automation only.

It rejects unsafe paths and obvious unsafe content patterns.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

The runner records required safety state:

- live_trading_required_status = DISABLED
- capital_deployment_required_status = BLOCKED

## Mission 42 Verification

Expected verification:

- Mission 42 unit tests pass
- dry-run sample pack works
- sample pack apply works without commit
- temporary sample files can be cleaned
- full offchain suite passes
- mission-control failure capture works
- Git remains clean after committed code/docs

## Verdict

Mission 42 improves development automation.

Future missions can be shipped as mission packs.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Use mission packs to reduce future mission execution to one generated pack plus one command.
