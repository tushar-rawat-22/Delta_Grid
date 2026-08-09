# Mission 101 — Research Reopening Governance

Mission 101 introduces the authority and custody machinery needed to make an
exact set of forward-observed market evidence eligible for future development
research. It stops at metadata-only admission. It does not execute a strategy,
calculate a return, produce a result bundle, train a model, generate a signal,
rank a candidate, or invoke Mission 95.

There is no validated profitable strategy and no selected candidate. Validation
and holdout access remain closed. ML, paper trading, live trading, exchange
accounts, credentials, signed requests, orders, portfolios, and capital remain
closed. The implementation did not initialize a production authority runtime,
build a production release, or issue a production permit.

The controlling contracts are
[`DELTAGRID_AUTONOMY_CONSTITUTION_V3.json`](../contracts/DELTAGRID_AUTONOMY_CONSTITUTION_V3.json)
and
[`DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json`](../contracts/DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json).
Version 3 preserves founder root authority and the permanent prohibition on
self-authorization. Its meaning of “research reopened” is deliberately narrow:
custody, dataset identity, finite permits, and admission reservation only.

## Evidence and custody chain

The bridge accepts only a Mission 100 ZIP backup previously exported from the
acquisition journal. It never accepts the mutable acquisition runtime. The
verifier bounds the archive, validates exact member names, sizes, hashes, and
the canonical manifest, materializes only declared regular files into a new
private temporary directory, opens the journal read-only, verifies its exact
schema, and reruns Mission 100 semantic verification including raw gzip and
decompressed-body hashes.

A `RUNNING` batch rejects the source. Failed batches remain inside the preserved
backup but contribute no admissible observations. Only observations attached to
complete authoritative batches enter the derived release.

Mission 100 and Mission 101 identities remain distinct. Each forward-custody
record retains the source batch ID, code commit, receipt hash, response hash,
source record hash, raw-object hash, body hash, payload hash, revision, and
supersedes lineage. It then derives a separate custody record hash under the
`DELTAGRID_M100_FORWARD_CUSTODY_V1` profile. The original evidence is never
rewritten into a Mission 99 legacy shape.

The backup natively attests the Mission 100 contract hash and capture code
commits. It does not attest the later remediation contract hash. Remediation
compatibility is recorded separately as a Mission 101 contract-review fact.
Local Git comparison proved that `48fc8bfd69792dbef00145e9f76c7e13a064d918`
is a documentation-only descendant of the already-reviewed Mission 100
implementation at `3d5fff9043ee4686e75b95c5b28c44e6e2928313`: only the root
README and two documentation files differ, while the acquisition package and
both Mission 100 contracts are byte-identical. Both exact commits remain in the
frozen allowlist; no branch, range, or wildcard is accepted.
Production activation remains blocked until the founder confirms that an exact
private backup's complete code lineage belongs to the reviewed compatibility
set.

## Independent certification

A forward release contains the exact source backup bytes, a canonical
metadata-only release document, and a certificate. Publication uses a private
same-filesystem staging directory and an atomic rename; existing output is never
replaced. Certification reloads the staged or published files, reverifies the
backup from scratch, reconstructs every derived custody identity and the release
core, and compares the stored certificate. The certifier has no repair path.

`available_at`, `first_observed_at`, and initial `last_verified_at` retain the
actual Mission 100 receipt time. Event time never substitutes for availability.
Only healthy-clock observations can carry `OBSERVED_LIVE`. Revision parents are
mapped explicitly from source identities to separate custody identities.
Machine-readable certification output contains IDs, hashes, counts, profile,
status, and booleans, not protected market values.

## Exact development datasets

A development dataset descriptor binds one certified release ID, release core
hash, certificate hash, provider, explicit symbol and stream lists, a canonical
`stream_intervals` mapping, inclusive event-time bounds, causal availability
cutoff, and the sorted exact set of selected custody record hashes. Mapping keys
must exactly equal the selected streams. Bar streams derive `"1h"`; funding
rates derive `null`. Operators cannot choose these values, and bars and funding
may coexist in one immutable descriptor. Its dataset ID and descriptor hash are
canonical. Wildcards are rejected, and a later release cannot enlarge an
existing descriptor. For each logical custody observation, the descriptor
selects exactly one chain head: the latest revision whose `available_at` is no
later than the causal cutoff. A later revision cannot displace its predecessor
at a cutoff before that revision became available.

The only permitted class and split are `REAL_MARKET_DEVELOPMENT`. Validation
and holdout descriptors are rejected.

## Permit trust boundary

The private authority runtime defaults generically to
`~/.deltagrid/research_authority`, outside the repository. It requires an
absolute non-symlink path, including rejection of dangling lexical symlink
components, `0700` directories, `0600` files, an exact SQLite
schema, immutable permit rows, and append-only events. It exposes no update,
delete, or reset operation. Tests use temporary paths only.

This is a single-user, same-OS-user trust boundary. The `FOUNDER` issuer role is
a governance label, not cryptographic authentication. Local filesystem
permissions and an exact write acknowledgement are part of the current trust
model. Mission 101 does not invent a signing system.

A permit binds the autonomy and Mission 101 contracts, an independently
observed clean DeltaGrid repository HEAD,
exact dataset and release identities, one experiment family, one development
stage, a fixed positive trial budget, trusted local-system UTC issuance time,
and finite expiry. The CLI accepts neither a repository commit nor an issuance
time. Revocation is append-only and uses trusted local-system UTC; the CLI
accepts no revocation time. Historical verification applies revocation only at
or after its event time. Expiry and exhaustion are derived states; consumed budget cannot
be resurrected. The fixed budget is global to the permit. Each capacity-approved attempt
atomically appends a deterministic consumption record in the private authority
runtime, binding the permit, Mission 94 trial, request hash, budget ID, and
trusted reservation time. Changing ledger files, budget IDs, processes, or CLI
invocations cannot reset this capacity, and consumption is never refunded.
Revocation and capacity reservation serialize through the same authority
SQLite write transaction. A revocation committed first blocks capacity; a
capacity reservation committed first is already authorized and its
metadata-only admission may finish.

## Admission V2 and stop boundary

Admission V2 independently verifies both the exact descriptor and the currently
applicable permit. It reuses the unchanged Mission 94 trial ledger and its
reserve-before-substantive-check semantics. Therefore, a failure after
reservation consumes that trial and appends a terminal `STOPPED` event.

The Mission 101 wrapper accepts that ledger only through an absolute,
non-repository, non-symlink path with a `0700` immediate parent, a `0600` bounded
file, and the exact Mission 94 SQLite tables, indexes, and triggers. Existing
ledgers are inspected read-only before the unchanged Mission 94 class is opened;
missing or extra schema is never repaired into acceptance. Admission authority
uses a trusted local UTC system-clock decision time, injectable only at the
Python construction boundary for deterministic tests. The request's historical
`created_at` remains hash-bound but cannot revive expired authority, and a
future request timestamp fails closed.
Admission also independently observes the exact DeltaGrid repository root,
40-hex HEAD, and untracked-inclusive working-tree status. A dirty checkout or
a request whose hashed repository evidence differs from that observation fails
closed. `admit-development` accepts neither `--repository-commit` nor
`--repository-clean`.

Admission reads metadata only. It has no artifact path for normalized market
values and imports no simulator, strategy, result engine, training, network, or
trading package. An `ADMITTED` decision means only that a finite trial slot has
been reserved for a future separately authorized runtime.

Mission 102 is the next planned mission. It must provide the general permitted
execution runtime under a separate reviewed contract before any result-bearing
development experiment can run.

## Operator CLI

The canonical foreground boundary is `python -m offchain.research.reopening`.
It emits canonical JSON. Ordinary failures emit only a stable reason token and
status, without a traceback or supplied private path. It has no network, URL,
plugin, shell, SQL, Python-evaluation, generic file-loading, strategy,
simulation, or result-execution command.

The read-only commands are:

- `show-contract`
- `verify-backup-source`
- `plan-forward-custody-release`
- `certify-forward-custody-release`
- `verify-development-dataset`
- `verify-development-permit`
- `inspect-authority-runtime`

`verify-development-permit` is explicitly read-only historical inspection at
the supplied `--as-of` time. It reads the authority runtime's canonical global
consumption count and accepts no caller-supplied consumption count.
Before issuance, verification returns `PERMIT_NOT_YET_ACTIVE`; from issuance
until a recorded revocation it may be active; at or after revocation it returns
`PERMIT_REVOKED`, subject to independent finite-expiry enforcement.

`verify-backup-source` combines source verification and compatibility review.
Its exact top-level metadata projection is `schema_version`,
`source_backup_sha256`, `source_manifest_hash`, `source_contract_identity`,
`source_attests_mission100_remediation_contract_hash`,
`mission101_compatibility_policy`, `batch_status_counts`,
`capture_batch_count`, `distinct_code_commits`,
`code_commit_compatibility`, `admissible_observation_count`,
`compatibility_verdict`, `reason_token`, and `metadata_safe`. Source-attested
Mission 100 identity remains separate from the Mission 101 review policy. The
projection contains no market values or normalized payloads.

The write-producing commands and their exact acknowledgements are:

- `build-forward-custody-release` — `BUILD_M101_FORWARD_CUSTODY_RELEASE`
- `create-development-dataset` — `WRITE_M101_DEVELOPMENT_DATASET_DESCRIPTOR`
- `init-research-authority-runtime` — `INITIALIZE_M101_RESEARCH_AUTHORITY_RUNTIME`
- `issue-development-permit` — `ISSUE_M101_DEVELOPMENT_PERMIT`
- `revoke-development-permit` — `REVOKE_M101_DEVELOPMENT_PERMIT`
- `register-development-budget` — `REGISTER_M101_DEVELOPMENT_TRIAL_BUDGET`
- `admit-development` — `RESERVE_M101_DEVELOPMENT_ADMISSION_TRIAL`

Budget registration is exposed because Admission V2 intentionally reuses the
unchanged Mission 94 trial ledger and admission cannot reserve an undefined
budget. It creates no second budget store. `admit-development` performs the
reservation and returns a metadata-only decision whose
`execution_authorized` field remains false; there is no execution continuation.
