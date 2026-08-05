# Autonomous Research Director v1

Mission 98 adds a deterministic, local Research Director that recommends one
next step from verified evidence and a fixed policy. The controlling machine
contract is
[`DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR_V1.json`](../contracts/DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR_V1.json).
The contract controls any conflict with this explanation.

The Director is decision-only. It does not perform research, activate a
contract, inspect market or protected artifacts, train a model, generate a
signal, construct a portfolio, access an exchange or credential, place an
order, paper trade, live trade, or deploy capital. Every output is a
non-executable recommendation that still requires the appropriate external
review and later versioned authority.

## Architecture

One request names a published Mission 97 observation manifest and may name one
metadata-only research-opportunity dossier. The Director:

1. strictly parses the request and optional dossier;
2. verifies the Mission 93–98 governance chain;
3. reads the manifest and its exactly derived Mission 97 snapshot and
   verification artifacts;
4. independently verifies their byte hashes, canonical hashes, identities,
   projections, authority declarations, health, incidents, and path bindings;
5. evaluates the immutable ordered policy;
6. constructs one canonical recommendation;
7. asks the separate verifier to recompute the complete decision; and
8. either returns a preview or, through `ResearchDirectorService.record`,
   verifies again immediately before atomically appending the package to
   SQLite.

The evidence loader never opens the research-ledger path, the result-root path,
or any market, result, model, strategy, or protected artifact referenced by the
snapshot. Those values are identity declarations only.

## Fixed recommendation registry

The action registry contains exactly seven tokens, in this order:

1. `STOP_NO_ADMISSIBLE_ACTION`
2. `REQUEST_OBSERVATION_REFRESH`
3. `REQUEST_MISSING_INTAKE_EVIDENCE`
4. `REJECT_PROPOSAL_OVERLAP`
5. `REJECT_POLICY_CONFLICT`
6. `DRAFT_RESEARCH_REOPENING_CONTRACT`
7. `QUEUE_FOUNDER_REVIEW`

The registry is compiled from immutable values. There is no registration,
mutation, plugin, dynamic import, caller-code, or executable-action interface.
A recommendation cannot change authority.

## Ordered decision policy

Exactly one of these rules wins, in order:

1. `RULE_1_UPSTREAM_INTEGRITY_STOP` stops when verified upstream health is
   `INTEGRITY_FAILURE` or an incident is `ERROR` or `CRITICAL`.
2. `RULE_2_POLICY_CONFLICT` rejects a dossier that requests any stage beyond a
   draft reopening contract or requests any authority.
3. `RULE_3_OBSERVATION_REFRESH` requests a refresh when health is `DEGRADED` or
   `UNAVAILABLE`, or the observation is more than 86,400 seconds old. Exactly
   86,400 seconds remains fresh.
4. `RULE_4_NO_PROPOSAL` stops when no dossier was supplied.
5. `RULE_5_MATERIAL_OVERLAP` rejects material overlap with a rejected family.
6. `RULE_6_INTAKE_EVIDENCE_INCOMPLETE` requests the missing metadata required
   by the intake gate.
7. `RULE_7_DRAFT_CONTRACT_REQUIRED` recommends drafting a versioned reopening
   contract for an otherwise complete novel proposal.
8. `RULE_8_FOUNDER_REVIEW` queues a complete referenced draft for founder
   review.

The caller, configuration, and database cannot reorder these rules.

## Request and dossier boundaries

The canonical request binds the Mission 98 contract, repository commit,
caller-asserted repository cleanliness, observation manifest path and byte
hash, optional dossier path and byte hash, explicit normalized UTC timestamps,
requester, and its own canonical hash. `repository_clean` must be exactly
`true`; production code treats it as an assertion and does not invoke Git.
`FUTURE_AUTOMATION` is a recognized requester but gains no additional
authority.

The optional dossier records only proposal metadata: economic mechanism,
falsifiable claim, new-information identity, provenance and causal status,
overlap declarations, the requested stage and authorities, and an optional
draft-contract reference. References carry IDs and hashes, but Mission 98 does
not open them.

The recognized stages are draft-only, development research, validation,
holdout, paper trading, live trading, and capital deployment. Only
`DRAFT_REOPENING_CONTRACT_ONLY` is admissible. Recognizing the other tokens
allows a deterministic policy rejection; it does not authorize those stages.

Missing structural fields, extra fields, malformed values, duplicate JSON
names, invalid UTF-8, BOMs, non-finite numbers, unsafe paths, symlinks,
oversized files, and hash mismatches fail before a recommendation is created.
Permitted null, empty, and status values represent incomplete evidence and
reach Rule 6.

## Preview, record, and independent verification

`preview` performs the complete input, contract, evidence, policy, decision,
and independent-verification sequence. It writes nothing and consumes no
decision capacity.

`record` performs that same sequence from the external inputs again. It never
trusts a prior preview. `ResearchDirectorService.record` is the supported
mutation boundary; the ledger exposes no public raw-package write API and does
not accept a caller-created receipt. The ledger invokes the independent
verifier and creates the receipt itself immediately before opening the atomic
mutation. A verifier disagreement therefore occurs before `BEGIN IMMEDIATE`
and leaves all three package tables unchanged.

`ResearchDirectorVerifier` has its own policy implementation. It does not call
the service, share a service policy function, or trust the selected action,
reason, rule, explanation, identity, or hash. Its receipt uses
`decision_as_of` as `verified_at`; neither service reads the wall clock.

## Ledger durability, replay, and capacity

Initialization binds the exact governance repository root, Mission 97
observation-output root, Director input root, expected repository commit,
Mission 98 contract identity, schema, creation timestamp, busy timeout, and the
fixed capacity of 10,000 unique recorded decisions. Roots must already exist,
resolve exactly, and contain no symlink component. Reinitialization is
idempotent only when all metadata matches.

SQLite uses foreign keys, `DELETE` journal mode, `EXTRA` synchronous
durability, a bounded busy timeout, and `BEGIN IMMEDIATE` for every mutation.
Metadata, requests, decisions, and receipts have update- and delete-rejection
triggers. Schema verification creates the unchanged reference schema in an
in-memory SQLite database and requires the real database to have the exact
same SQLite-provided table, index, and trigger definitions, not merely the
same object names. Each operation opens and closes its own connection.

Before insertion and whenever a package is loaded, the ledger checks the
strict request and its bound commit and contract, the exact permitted
action/reason/rule outcome and fixed explanation, all compiled Mission 93–98
contract identities, proposal nullability and byte identity, deterministic
decision identity, and the exact verification token, version, timestamp,
recomputed outcome, hash, and identity. Ledger-only verification certifies
stored semantics and relationships; it cannot reconstruct historical
external evidence that is not stored in the database.

An exact replay revalidates the current request and external evidence, then
returns the byte-identical stored package without consuming another slot. A
conflicting request or decision identity fails closed. The 10,001st unique
decision is rejected, while exact replay remains available at capacity.

`status` is read-only. `verify-ledger` checks schema, metadata, indexes,
triggers, foreign keys, durability settings, hashes, relationships, package
semantics, completeness, and the fixed capacity invariant. It also requires
fresh metadata to equal the metadata bound to the opened ledger object and
rechecks the three resolved roots and identities.

The append-only guarantee depends on use of the supported API and the verified
SQLite schema. It is not a protection boundary against a process or user with
unrestricted filesystem access, in-process Python access, or source-code
control; such an actor could replace the whole database or alter the program.

## CLI

All commands are local foreground operations and require explicit timestamps.
They write canonical single-line JSON to stdout on success and stderr on a
controlled failure.

Initialize a database whose parent and three roots already exist:

```text
python -m offchain.research.director init \
  --database /absolute/path/director.sqlite3 \
  --observation-root /absolute/path/mission97-output \
  --input-root /absolute/path/director-input \
  --repository-root /absolute/path/deltagrid \
  --expected-repository-commit <40-lowercase-hex-commit> \
  --created-at 2026-08-05T00:00:00Z
```

Preview or record a request relative to the bound input root:

```text
python -m offchain.research.director preview \
  --database /absolute/path/director.sqlite3 \
  --request-relative-path requests/intake-001.json

python -m offchain.research.director record \
  --database /absolute/path/director.sqlite3 \
  --request-relative-path requests/intake-001.json
```

Inspect one package or the deterministic list, then verify the ledger:

```text
python -m offchain.research.director status \
  --database /absolute/path/director.sqlite3

python -m offchain.research.director status \
  --database /absolute/path/director.sqlite3 \
  --decision-id decision-...

python -m offchain.research.director verify-ledger \
  --database /absolute/path/director.sqlite3
```

## Failure and recovery

Input, evidence, clock, contract, decision, database, and capacity failures have
stable reason tokens and create no partial package. An interrupted SQLite
transaction is rolled back by SQLite. After an interruption, leave the database
and rollback journal together, confirm that the filesystem is available, and
run `verify-ledger`. Do not delete a journal, edit rows, recreate metadata, or
attempt repair in place. Restore a known-good complete database copy if
verification fails.

The operating targets are zero silent failure, zero uncontrolled action, and
zero unbounded loss. They are design objectives and boundaries, not a claim of
literal error-free operation.

## Continuous integration

`DeltaGrid CI` runs the complete off-chain test suite on Ubuntu 24.04 with
read-only repository permission. It validates the submitted commit range,
uses commit-pinned checkout and Python setup actions, prints Python and
dependency diagnostics, installs only `offchain/requirements.txt`, and uploads
no artifact. The requirements file intentionally contains a ranged pytest
dependency, so the environment is bounded and diagnosable rather than
bit-for-bit dependency reproducible.

## Future direction

Mission 98 supports future autonomous advancement by making the next
recommendation deterministic, independently verifiable, bounded, and durable.
It does not perform the research it recommends and cannot authorize itself.
Mission 99 is the next provisional stage: reproducible, certified,
availability-aware market datasets under a separate reviewed contract.
