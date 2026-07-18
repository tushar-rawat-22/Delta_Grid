# DeltaGrid operator guide

This is current internal operator guidance. It is subordinate to the
[final-freeze contract](../contracts/DELTAGRID_FINAL_FREEZE_V1.json), the
[final-freeze explanation](DELTAGRID_FINAL_FREEZE.md), and the current research,
risk, and safety policies. It is not a research or trading authorization
instrument.

## Purpose and current boundary

This guide covers safe local development and software verification in an
existing DeltaGrid checkout. DeltaGrid is a completed quantitative research
platform, but no validated profitable strategy exists, no candidate is
selected, and research is frozen. Paper trading is not currently authorized;
live trading is not authorized; capital deployment is blocked; and ML operation
and autonomous execution are not authorized.

## Supported operator commands

The supported current operator commands are exactly:

- `scripts/mission_control.py`, which builds and runs a local
  software-verification plan;
- `scripts/mission_pack_runner.py`, which validates and applies a reviewed local
  mission-pack JSON file and runs its declared verification plan.

These are development and verification interfaces, not research or trading
interfaces. Historical mission modules and machine-only research modules are
not supported current operator interfaces.

## Prerequisites

- Use an existing, configured DeltaGrid checkout with the repository root as
  the working directory. The repository does not currently promise a fully
  verified fresh-clone bootstrap.
- Use the project interpreter: `offchain/.venv/bin/python`.
- Invoke the mission-pack runner as the Python module
  `-m scripts.mission_pack_runner` from the repository root.
- Begin normal controlled work with a clean working tree.
- Read the current repository status and final-freeze documents before acting.
- Do not provide exchange credentials, private keys, or live account access;
  these local verification commands do not require them.

## Safe-start checklist

- Verify the repository identity.
- Verify the current branch and expected commit.
- Run `git status --short` and inspect every listed path.
- Read the relevant command help.
- Use dry-run first.
- Use temporary or reviewed local inputs.
- Inspect summaries and logs before proceeding.
- Obtain explicit approval before repository-writing, commit, or push actions.

## Local verification command

Read the published help before constructing a run:

```text
offchain/.venv/bin/python scripts/mission_control.py --help
offchain/.venv/bin/python scripts/mission_control.py verify --help
```

This safe dry-run records a local plan without executing its compile, pytest,
mission-command, or Git-status steps:

```text
offchain/.venv/bin/python scripts/mission_control.py verify --mission local-software-review --module-file scripts/mission_control.py --test-file offchain/tests/test_mission_control.py --mission-test offchain/tests/test_mission_control.py --mission-command "git diff --check" --log-dir /tmp/deltagrid-local-software-review --skip-full-suite --dry-run
```

The options have these effects:

- `--mission` is the required label used in the run directory and logs.
- `--module-file` optionally adds a Python compilation step for one module.
- `--test-file` optionally adds a Python compilation step for one test file.
- `--mission-test` optionally adds a focused pytest path.
- `--mission-command` optionally adds a local command after tests. It is parsed
  into arguments and passed directly to a subprocess, not through a shell.
- `--log-dir` selects the parent directory for the run summary and command logs;
  its default is `reports/mission_logs`.
- `--skip-full-suite` omits the otherwise included `offchain/tests` pytest run.
- `--require-clean-start` stops before plan execution when
  `git status --short` reports a dirty working tree.
- `--dry-run` writes planned commands into `summary.json` without executing
  them.

Without `--dry-run`, every selected compile, pytest, mission-command, and Git
status step can execute locally. Inspect and approve any supplied
`--mission-command` before use. Dry-run still creates a run directory and writes
its summary. Successful verification establishes only that the selected
software checks passed; it does not establish alpha or create authorization.

## Mission-pack command

Read both help views first:

```text
offchain/.venv/bin/python -m scripts.mission_pack_runner --help
offchain/.venv/bin/python -m scripts.mission_pack_runner run --help
```

The following is a template. Replace `<reviewed-local-pack.json>` with the path
to a pack that has been inspected and approved locally:

```text
offchain/.venv/bin/python -m scripts.mission_pack_runner run \
  --pack <reviewed-local-pack.json> \
  --dry-run
```

The options have these effects:

- `--pack` is the required path to the mission-pack JSON file that will be read
  and validated.
- `--repo-root` selects the repository whose declared files and local logs may
  be updated; its default is the current directory.
- `--dry-run` validates and summarizes the pack without applying declared file
  actions or executing its verification plan.
- `--commit` requests commits of only the code and documentation paths declared
  by the pack after successful verification.
- `--push` requests `git push origin main` after the preceding pack and requested
  commit stages succeed.
- `--no-clean-start` disables the normal clean-working-tree precondition. This
  weakens a safety check and should be used only for a documented reason after
  every existing change has been reviewed.

A pack may declare repository file writes. Inspect the complete pack before a
normal run, including its targets, modes, content, verification command, commit
paths, and messages. Dry-run applies none of those declared file actions and
runs none of the verification-plan commands, but it still writes a local
`summary.json` beneath the mission-log directory. `--commit` and `--push` are
repository operations and require explicit approval; neither flag authorizes
research or trading. Automatic push is not a safe default workflow.

## Files and outputs

The default output parent is `reports/mission_logs`. Each run creates a
`<safe-label>-<run-id>` directory containing `summary.json`.

For non-dry-run verification commands, each executed step also writes a `.log`
file. Its opening lines are a human explanation of the outcome, interpretation,
current safety boundary, and next safe action. The later
`Machine-stable command details` block records the step name, rendered command,
return code, timestamps, duration, `STDOUT`, and `STDERR` using stable field
labels.

Both CLIs print the same structured summary object as formatted JSON to stdout.
The summary contains machine-oriented verdict, counts, safety-status fields,
results, paths, and requested-action fields as applicable. Treat the explanatory
log prose as human guidance and the JSON and machine-stable fields as structured
output; neither form creates authorization.

## Reading outcomes

- **PASS** means a software or verification step satisfied its stated check.
- **FAIL** means a command or software requirement failed.
- **REJECT** means a research hypothesis or candidate missed a frozen research
  gate; it is not a synonym for a software-command failure.
- **STOP** means execution deliberately halted because a prerequisite or safety
  condition was not satisfied.
- **BLOCKED** or **NOT AUTHORIZED** means a later stage cannot proceed under the
  current authority.

PASS does not imply profitability, candidate selection, or permission for
research, paper trading, live trading, capital, ML, or autonomous execution.

## Failure and recovery

1. Stop further repository-writing actions.
2. Inspect the JSON summary.
3. Inspect the relevant command log.
4. Inspect the recorded `STDOUT` and `STDERR`.
5. Run and inspect `git status --short`.
6. Correct the local software or input issue without discarding unknown work or
   evidence.
7. Rerun command help or dry-run.
8. Rerun the smallest authorized verification that addresses the issue.
9. Do not bypass safety gates merely to obtain PASS.

## Git actions and approvals

Mission-control clean-start checking is opt-in through
`--require-clean-start`; mission-pack clean-start checking is enabled by default
unless `--no-clean-start` is supplied. The pack runner stages only the declared
code or documentation commit paths when an explicit `--commit` is present. An
explicit `--push` targets `origin main` under the existing implementation.

Before committing, review the declared paths, staged paths, and complete diffs.
Before pushing, obtain explicit approval and stop if the remote has moved. The
implementation provides no force-push workflow, and this guide does not
authorize one. Repository success cannot create research, trading, or capital
authority.

## Actions this guide does not authorize

- New research is not reopened by this guide.
- Paper trading is not currently authorized.
- Live trading is not authorized.
- Capital deployment is blocked.
- ML operation is not authorized.
- Autonomous execution is not authorized.
- Validation or holdout access is not authorized.
- Exchange orders, transaction signing, private-key use, and account access are
  not authorized.
- A command, report, test, model, score, review, or dashboard cannot
  independently change authorization.

Future strategy research requires a new versioned reopening contract.
Historical next actions do not override the final freeze.

## Related documentation

- [Documentation home](README.md)
- [Final-freeze explanation](DELTAGRID_FINAL_FREEZE.md)
- [Research policy](RESEARCH_POLICY.md)
- [Risk policy](RISK_POLICY.md)
- [Safety invariants](SAFETY_INVARIANTS.md)
- [Future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md)
- [Research and evidence summaries](research-summaries/README.md)
- [Documentation registry](documentation-status.json)
- [Project overview](../README.md)
