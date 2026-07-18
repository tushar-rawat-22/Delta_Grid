# ADR-0041: Local Mission Automation Harness

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

DeltaGrid missions have become repetitive:

- create files
- compile
- run mission tests
- run full offchain suite
- run mission command
- inspect git status
- collect outputs

The project needs local development automation before further research automation.

## Decision

Add a local mission automation harness.

Files:

- scripts/__init__.py
- scripts/mission_control.py
- offchain/tests/test_mission_control.py

Code commit:

- df295d1 Add local mission automation harness

The harness supports:

- command execution
- log writing
- dry-run mode
- mission verification plans
- compile checks
- mission test execution
- full suite execution
- mission CLI execution
- git status checks
- JSON summaries

## Safety

The harness is development automation only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

The harness records required safety state:

- live_trading_required_status = DISABLED
- capital_deployment_required_status = BLOCKED

## Mission 41 Verification

Expected verification:

- Mission 41 unit tests pass
- full offchain suite passes
- dry-run mode works
- harness can verify itself
- logs are written under reports/mission_logs
- Git remains clean after committed code/docs

## Verdict

Mission 41 improves development velocity and repeatability.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Use automation harness to accelerate future missions.
