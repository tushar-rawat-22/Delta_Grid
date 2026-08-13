# Independent statistical and protected-evidence governance

Mission 103 supplies governance infrastructure for a finite development
program and a single fixed candidate's possible progression through
`REPLICATION`, `VALIDATION`, and `HOLDOUT`. The controlling contracts are
Autonomy Constitution v5 and
`DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json`.

This implementation did not create a campaign, admit a program, select a
candidate, execute research, materialize or open protected evidence, or issue a
stage authorization. Both production registries were deliberately empty at
Mission 103 publication. The later prospective RAB-1 contract registers one
exact statistical adapter and one exact protected evaluator without changing
the Mission 103 contract. The founder must still authorize each protected
stage separately.

## Campaign admission and the anti-reset boundary

A proposal commits the repository commit, economic lineage, evidence epoch and
cutoff policy, the complete family and inferential-hypothesis universes, total
result-guided capacity, maximum program count, expiry, and controlling
contracts. Canonical commitment happens before founder admission. Campaign
admission generates no statistical randomness. After the complete program is
frozen and its immutable `program_hash` exists, a separate acknowledged founder
activation revalidates the protocol, campaign validity, and prospective
protected boundaries. Only then does it generate the sole unpredictable
256-bit nonce and bind it to the exact proposal and program. Activation is
one-use; normal APIs and inspection never return the nonce.

The private database makes proposal admissions one-to-one and gives the
lineage-plus-evidence policy an anti-reset key. Reusing a proposal or presenting
the same lineage and evidence epoch as another admission fails closed. A
terminal campaign cannot create another program. Software does not decide that
a renamed or slightly changed proposal is novel: a genuinely new campaign
requires another founder-issued admission with explicit lineage.

Display names do not define statistical identity. Each declared hypothesis
has a semantic hash over family and variant hashes, recursively frozen
parameters, execution identity, exact M94/M101/M102 bindings, and statistical
adapter hash. Cosmetic family, variant, hypothesis, or execution labels cannot
change that semantic hash or obtain new null randomness.

The declaration is chronologically pre-result: it binds the M94 reservation,
request and budget; M101 permit, dataset, descriptor, release core and
certificate; and only stable M102 identities—the repository commit, registry
snapshot, family and variant definitions, recursively frozen parameters,
execution model and risk identities, and controlling contracts. It cannot
contain a future M94 result-link hash, M102 result hash, or final M102 execution
specification ID/hash. That specification includes M102's runtime-generated
`authority_decision_time`; its ID/hash are appended as post-result evidence
only after real finalized replay verification and then copied into the selected
candidate.

## Frozen program and development evidence

Mission 103 V1 permits exactly one program per campaign. It may be created only
while the campaign is `ADMITTED`; freezing it immediately consumes that
capacity. The immutable protocol binds the exact repository commit, complete
hypothesis and execution universe, primary statistic and direction, null policy
and adapter-bound algorithm, alpha, repetition count, hard gates, ranking and
tie-break rules, exact execution and risk hashes, all three protected partition
specifications, protected engine identities, custody-source policy and
acceptance rules. JSON numbers that affect economics or statistics use exact
strings; binary floats are rejected.

Here, `m` is the number of distinct declared inferential hypotheses across the
entire program, not the number in one economic family. Any result-guided
configuration that can influence selection occupies one member of `m`.
Technical recovery of the exact same deterministic execution is not a new
hypothesis, does not enlarge capacity, and cannot obtain new randomness. M103
does not accept caller labels such as `FAILED`, `CRASHED`, or `MISSING`.
Success is derived from M102 full replay plus exact M94 completion and result
linkage. Failure receives p-value 1 only when the exact M94 ledger proves M102's
terminal failure reason after an execution-spec claim and no finalized result
link exists. An attempt without either proof remains nonterminal and blocks
qualification. Every member must be terminal before program-wide selection;
early-success stopping is prohibited.

M103 does not consume a caller-asserted verification summary or terminal state. Its internal
bridge calls the real Mission 102 full-replay verifier, then reads the canonical
execution specification and result artifact plus the verified M94 finalization
link. It cross-binds exact M94 trial, request, budget and result-link identities;
M101 permit, dataset and descriptor identities; M102 execution specification,
registry, result and repository commit; family, variant, recursively frozen
parameters; and cost/execution identity. An undeclared, unfinalized, altered,
or historical-code result cannot enter selection. Canonical timestamps enforce
proposal commitment ≤ campaign admission ≤ program freeze ≤ founder activation
≤ M102 `authority_decision_time` ≤ M94 completion/result linkage. Import time is
irrelevant; a result whose execution authority predates activation is rejected.

## Exact statistics

The one-sided empirical p-value is
`(1 + count(null outcome at least as favorable as observed)) / (R + 1)` and
can never be zero. The protocol must satisfy
`R >= max(5000, ceil(m / alpha) - 1)` before result inspection. The
implementation uses integers, `Decimal`, and rational arithmetic rather than
binary float. In particular, `m=251`, `alpha=0.05`, `R=5000` fails because the
required value is 5019. Exact enumeration uses `R=0` when the preregistered
finite null space is sufficiently small. Its exact configuration IDs and
observed configuration are committed in the adapter's semantic definition
before results; the adapter must return one result for every configuration in
that exact order. For empirical nulls M103—not the adapter—uses
`SHA256_COUNTER_V1` to construct `R` ordinal/u256 draws and a plan commitment.
The adapter receives that immutable plan and must return one statistic carrying
each exact ordinal and draw. M103 rejects missing, added, reordered or replaced
draws. The frozen primary-statistic measurement must equal the null evidence's
observed statistic under exact `Decimal` semantics.

Holm step-down correction runs once across all `m` hypotheses. Ordering is by
exact p-value and then identifier for deterministic handling of ties. Adjusted
evidence is monotone, and rejection stops at the first missed Holm threshold.
Hard gates and the frozen ranking rule run only after all results are terminal.
Ranking is an exact numeric vector derived by M103 from frozen measurement IDs,
followed by the semantic hypothesis hash tie-break; adapter pass/rank labels are
not accepted.
At most one candidate is frozen with its full campaign, program, repository,
governed-result evidence hash, verified-result hash, final M94/M102 identities,
primary and measurement commitments, null and plan/enumeration commitments,
Holm, gate, ranking, parameter, cost/execution and risk identities. Large null
transcripts remain in append-only result evidence rather than being duplicated
in the candidate. A later protected-stage failure cannot promote the runner-up.

Stochastic null seeds are unavailable before exact-program activation. They use
SHA-256 with the contract-bound `DELTAGRID_M103_NULL_SEED_V1\0` domain, the
founder activation nonce, proposal hash, already-frozen program hash, semantic
hypothesis/family/variant hashes, adapter hash, and PRNG
version. The exact preimage is domain bytes, then the 32-byte nonce, then direct
UTF-8 canonical JSON bytes for the input object; there is no intermediate hex
hash of that JSON. A proposer-controlled display label alone cannot change the
seed. The
specified deterministic generator is `SHA256_COUNTER_V1`; it is a reproducible
primitive, not the source of admission entropy.

## Prospective protected partitions

Before development selection, the protocol freezes exact future UTC boundaries
for all three stages. Each specification binds exact stream:symbol pairs and
per-stream native intervals (including null funding intervals),
context start, scoring start/end, availability cutoff, sample range,
millisecond purge/gap/embargo and forward horizon, certification,
availability and disjointness policies. Every scoring start must be future at
program creation and again at founder activation. Scored intervals are ordered
and pairwise disjoint. No common stage cost hash is frozen: possible hypotheses
may have distinct execution hashes, and the selected candidate's verified M102
execution identity alone controls protected execution.

Context ends before `scoring_start-gap_ms-purge_ms-forward_horizon_ms`; scored
records end at `scoring_end-forward_horizon_ms`. A later stage's context cannot
begin before the prior scoring end plus prior horizon and embargo plus its own
gap. Exact scored sets are disjoint. These exclusions are applied while deriving
record sets, not retained as labels. Under `CONTEXT_AS_OF_SCORING_START_V1`, a
context record must also have `available_at` strictly before scoring start. An
old economic event first available at or after that boundary is excluded rather
than floored earlier or silently moved.

A future window can be bound only after scoring closure and its frozen
availability cutoff. Callers provide only the M101 custody source. M103 invokes
the M101 envelope verifier, thereby revalidating the M99/M100 lineage, and
internally derives exact context and scored custody-record sets. Their hashes
and counts are stored separately; duplicate scored hashes across stages fail
even if numeric intervals appear disjoint. Materialization never accepts
caller-asserted counts, coverage hashes, closure labels, or value payloads. The
custody root is precommitted. The verified M100 backup manifest must postdate the
cutoff and its checkpoint for every exact pair must extend beyond the cutoff;
otherwise materialization fails closed. `exact_observable_inputs` remains the
preregistered maximum allowed stage universe. Separately,
`present_observable_inputs` is the sorted unique set of stream:symbol pairs
reconstructed from the verified custody metadata of the exact context and
scored record-hash union. That actual set is inside `materialization_hash` and
must be a subset of the allowed universe. Once the candidate is fixed, all of
its M102 `observable_inputs` must be present in that actual materialized set;
this metadata-only gate runs before authorization is issued and is repeated
immediately before one-use authorization consumption and `OPENED`.
After durable opening, the loader recertifies release and source integrity but
parses payload JSON only for the committed ordered context hashes union ordered
scored hashes. Purged, gap, delayed-context, out-of-set, and cross-pair payloads
are never parsed. Economic execution uses M102's
causal `available_at` then custody-hash order, never lexical hash order alone.
Normal status, logs, errors and CLI JSON expose only identities, hashes, counts
and states. M103 has no generic URL loader and no arbitrary filesystem command
for protected data.

## Evaluator, authorization, opening and recovery

The protected-evaluator registry is separate from the statistical-adapter
registry. Both are static and sealed, and both have zero production entries at
Mission 103 completion. Runtime callables, module paths, plugin directories,
dynamic imports, `eval`, `exec`, and generated arbitrary Python are not
eligible. Public APIs never accept a registry object. Service hashes are
derived from their exact semantic definitions instead of accepted as arbitrary
constructor claims. Tests replace narrow internal resolver seams; there is no
importable test registry builder. Ordinary in-process Python is not described
as a sandbox.

Each stage needs its own exact one-use founder authorization. The exact M102
candidate executor and deterministic measurement engine are frozen in the
pre-result program; authorization derives them and cannot substitute another.
It binds the
campaign, program, fixed candidate, stage, specification, materialization,
repository commit, evaluator, previous terminal decision, issue and expiry
times, and controlling contract hashes. Trusted issue time is obtained inside
the authority service. Wildcards, caller-selected trusted time, self-issuance,
reuse, stale authorization and revoked authorization fail closed.

Opening uses `BEGIN IMMEDIATE`. The database consumes the authorization,
persists `STAGE_OPENED`, creates the immutable execution identity and commits
before the internal exact-materialization loader is invoked. No public opening
or recovery API accepts a payload loader. A crash before commit leaves no
opening and
does not expose values. A crash after commit leaves the stage permanently open
and capacity consumed. Recovery can evaluate only that same execution after
proving its exact execution hash; it cannot change candidate, code, evaluator,
window, protocol, inputs or randomness. M103 reconstructs the selected family,
variant, parameters and registry snapshot, then reuses the Mission 102 strategy,
fill, position-effective-time, Decimal and accounting kernel. Context invokes
only strategy warming; its intents are discarded and no context accounting
kernel exists. Scoring starts a new M102 kernel at the variant's initial NAV
with zero positions, so development or prior-stage positions, fills, costs,
funding and PnL cannot carry over. Only scored events create the authoritative
ledger and metrics. The evaluator receives only that ledger commitment and
metrics, and its reported measurements must exactly equal the authoritative
metric values. Context supplies M102's reveal count—zero for the first
candidate-observable context event, one for the second, and so on—while
non-observable events do not advance it. The same warmed underlying strategy
adapter reaches scored execution through a protected-only delegation wrapper.
The wrapper changes only `revealed_event_count`: the first scored event sees the
number of candidate-observable context events, and later scored events add the
number of prior authoritative ledger event rows. The scored M102 kernel itself
is still new and financially flat; no context position, cash change, intent,
fill, fee, slippage, funding, turnover, PnL, exposure, or equity change crosses
the boundary. Execution evidence binds both the candidate-observable context
event count and the candidate-observable scored event count.

For Mission 103 V1, `minimum_scored_samples` means exactly the minimum number
of candidate-observable scored event rows in the authoritative selected-
candidate M102 ledger. Materialization-wide records for unused preregistered
streams cannot satisfy it. This is an execution-coverage and resource gate, not
a claim about unique timestamps, trades, fills, independent observations, or
effective statistical sample size. Protected acceptance statistics and gates
support only the canonical Decimal-text M102 metrics: initial research NAV,
final equity, gross PnL, fees, slippage costs, funding cash flow, net PnL,
turnover, gross and net exposure, peak equity, and maximum drawdown.
`unfilled_intent_count` remains an M102 result metric but is not part of the M103
V1 protected acceptance language. A protocol using it is rejected when the
program is frozen. Execution and measurement are each repeated and compared
before a decision, excluding nondeterministic recovery chances.

A pass makes the fixed candidate eligible to request—not automatically receive—
the next founder authorization. A failure terminally rejects the program with
no retuning, reranking, fallback, shifted partition or second attempt. A passing
holdout emits only `QUALIFIED_FOR_M104_OBSERVATION` with
`authority_effect = NONE`.

## Private runtime and operator inspection

The proposed production root is
`~/.deltagrid/statistical_governance`, containing one `governance.sqlite3`.
Initialization requires an explicit acknowledgement. Roots must be absolute,
outside the repository, free of symlink components, and mode 0700; the database
is mode 0600. The schema is exact, transitions are append-only, and update,
delete and reset APIs are absent.

The normal CLI supports contract display, sealed-registry inspection,
metadata-only state inspection, and explicit empty-state initialization. It
does not admit campaigns, open protected values, dynamically load code, or
accept generic paths or URLs for evidence.

## Authority ceiling

`QUALIFIED_FOR_M104_OBSERVATION` is eligibility evidence only. It does not
authorize M104 observation, model or ML training, paper trading, live trading,
exchange or credential access, signed requests, orders, portfolio allocation,
larger leverage or risk, capital deployment, or self-authorization. A campaign,
program, candidate, alpha, profitability, protected opening, validation pass,
holdout pass and M104 authorization do not exist merely because this
infrastructure exists.
