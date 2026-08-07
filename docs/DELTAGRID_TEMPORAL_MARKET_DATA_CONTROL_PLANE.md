# Temporal Market Data Control Plane v1

Mission 99 adds the custody layer that future research will use to identify
exactly which market-data evidence was available at a decision time. It does
not collect fresh data, calculate returns, run a strategy, train a model,
produce signals, access an exchange, place orders, paper trade, live trade, or
deploy capital.

The controlling machine-readable contract is
[`DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json`](../contracts/DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json).
Its canonical content SHA-256 is
`159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c`.
The ordinary file-byte SHA-256 is
`63d55510d49ed77b62a55dc198953cedefb083372a685244ad8413e55b9d432c`.

## Temporal model

A record keeps market time separate from data availability. For hourly bars,
`event_time` is the completed bar close/end timestamp, not the bar opening
instant. For settled funding, `event_time` is the funding timestamp.
`source_time`, when present, is a provider-declared completion or publication
time. `available_at` is the earliest time the record is allowed into an as-of
causal resolution.

Availability has four explicit classes:

- `OBSERVED_LIVE` requires a healthy local clock and a forward-capture receipt.
  Its availability and first-observed timestamps are the receipt time.
- `SOURCE_DECLARED` requires a defensible source timestamp and cannot become
  available before that timestamp.
- `CONSERVATIVE_RECONSTRUCTION` is a versioned assumption. Mission 99 activates
  no production reconstruction policy.
- `UNKNOWN` has no `available_at` value and cannot be resolved causally.

Mission 86 is historical backfill evidence. It did not record the forward
request-start and monotonic timing needed to recreate a live observation, so
Mission 99 does not fabricate those fields. Imported Mission 86 observations
remain `UNKNOWN` unless a later, separately reviewed policy provides a
defensible alternative.

Corrections append immutable revisions. Earlier revisions remain in the
snapshot. Missing parents, forks, cycles, changed logical identities, policy
changes inside a revision chain, and backward-moving timestamps fail closed.
Exact duplicate input is idempotent; conflicting duplicates are rejected.

## Receipt and raw-object evidence

Forward and legacy acquisition evidence use separate receipt schemas.
`FORWARD_CAPTURE_V1` records request identity, request and receipt times,
monotonic duration, clock health, HTTP/retry metadata, response hashes,
collector identity, and repository identity. `LEGACY_CAPTURE_V1` records only
the fields that Mission 86 actually retained.

Raw responses live in a shared content-addressed store under the runtime root.
Every stored object must be a valid gzip member. Certification recomputes both
the compressed-object SHA-256 and the decompressed response-body SHA-256, then
checks the receipt and every observation derived from that response. Raw bytes
are never inferred from the normalized database.

## Runtime layout

The production default is `~/.deltagrid/market_data`, outside the Git checkout.
The v1 layout is:

```text
catalogue.sqlite3
objects/sha256/<prefix>/<sha256>.gz
releases/<release-id>/manifest.json
releases/<release-id>/release.sqlite3
releases/<release-id>/certificate.json
staging/
incidents/
locks/publication.lock
```

Runtime directories use mode `0700` and runtime files use `0600` on the
supported macOS/POSIX target. Symlink components, path traversal, roots inside
the repository, unexpected output replacement, malformed JSON, and unsupported
SQLite schemas are rejected. SQLite files use a frozen narrow schema rather
than the historical multi-purpose `offchain/deltagrid.db` schema.

## Release identity and publication

Mission 99 v1 uses `FULL_SNAPSHOT_V1`. A child carries the complete effective
observation and receipt history inherited from its parent plus valid additions
or revisions. Raw gzip objects are shared by content hash rather than copied
between releases. Synthetic and real lineages cannot be mixed.

The semantic release core does not contain its own ID or hash. DeltaGrid first
canonicalizes that core, hashes it with SHA-256, and derives the release ID as
`m99-<release-core-hash>`. Publication time, staging names, absolute paths, and
SQLite byte layout are not part of semantic identity.

Publication is single-writer and foreground-only. A POSIX `flock` covers the
complete critical section. The publisher writes and verifies a same-filesystem
staging directory, writes the independent certificate, fsyncs the evidence,
atomically renames the complete directory, verifies the published release, and
only then inserts a certified catalogue row. Resolvers discover releases only
through those catalogue rows. A crash after rename but before catalogue commit
therefore leaves an orphaned release rather than a partially visible release.
Evidence is retained for operator inspection; Mission 99 never deletes or
repairs it automatically.

The file lock is a cooperative same-host writer control, not a security sandbox.
Code running as the same trusted OS user can still import internal Python
modules. Strong process isolation, restricted service credentials, and execution
authorization belong to later founder-approved missions; Mission 99 does not
pretend underscore-prefixed Python APIs provide that boundary.

## Independent certification

The staged verifier and public final certifier are separate. The public certifier
accepts published release directories only and reloads persisted bytes instead of
trusting builder output. It verifies the current contracts, exact SQLite schema,
manifest, certificate,
raw-object hashes, gzip bodies, receipt schemas, observation hashes, temporal
rules, revision chains, parent snapshot inheritance, source-contract lineage,
resource limits, and the closed research/trading boundary. `certificate.json`
is mandatory for final certification and the certifier never creates or repairs
it.

The catalogue and release SQLite materialization are indexes. They do not
replace the immutable raw objects, receipts, release semantic core, and
certificate as evidence.

## Legacy audit and migration boundary

`audit-legacy` is read-only and metadata-safe at its output boundary. It verifies
the locked Mission 85 contract, Mission 86 response/manifest lineage, exact raw
gzip and body hashes, Mission 87 certificate lineage, exact table counts, and
the normalized series hashes already frozen by Mission 87. Recomputing those
series hashes necessarily reads the stored values as custody-integrity evidence;
it does not expose them, calculate performance, or grant development, validation,
or holdout research access. Printable audit output is limited to IDs, hashes,
counts, paths, statuses, booleans, and elapsed time.

The real legacy builder is deliberately separate from the synthetic publisher.
It requires the exact `BUILD_LEGACY_RELEASE` acknowledgement, a clean repository
at the current code identity, and two matching legacy audits around input
extraction. The resulting release persists the metadata-only audit proof core as
well as its canonical proof hash, so the custody decision is self-describing
without exposing market values. Mission 99 acceptance does **not** execute that
migration. Real-data research resolution remains disabled even after a legacy
custody release is built.

## Resolver and recovery

The v1 resolver permits only `SYNTHETIC_TEST_ONLY`. It independently certifies
the selected catalogue release, excludes records whose `available_at` is later
than the decision time, selects the latest eligible revision, and returns
record identities rather than normalized market values. `UNKNOWN` availability
and every real-data release fail closed.

Recovery inspection is read-only. It identifies incomplete or valid staging,
orphaned raw objects, orphaned releases, dangling or invalid catalogue entries,
publication-lock state, and incident evidence. It neither deletes nor repairs
anything.

## Finite bounds

The contract fixes one provider, three allowlisted hosts, three symbols, five
streams, one bar interval, and zero Mission 99 network requests. The legacy
acceptance inventory is exact: 276 raw responses, 262,656 market bars, 8,208
funding observations, and 15 certified series.

Runtime limits include 8 MiB per compressed object, 32 MiB decompressed per
response, 128 MiB total raw-object storage for Mission 99 acceptance, 300,000
release rows, 300 receipts, a 256 MiB release SQLite limit, a 320 MiB staging
limit, a 512 MiB total acceptance-runtime limit, four releases, and a two-second
publication-lock wait. These are engineering bounds, not permission to collect
additional data.

## Authority

Mission 99 can custody data, run a metadata-safe legacy audit, build synthetic
test releases, certify them, inspect recovery state, and resolve authorized
synthetic evidence. It cannot authorize itself or any later research/trading
stage. Founder-root authority and the permanent self-authorization prohibition
are defined in the [Autonomy constitution](DELTAGRID_AUTONOMY_CONSTITUTION.md).
