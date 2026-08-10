# DeltaGrid public projection

Platform Mission P1 begins with a deliberately small read-only boundary between the quantitative core and a future public web application.

The controlling machine contract is [`DELTAGRID_PUBLIC_PROJECTION_V1.json`](../contracts/DELTAGRID_PUBLIC_PROJECTION_V1.json).

## What P1.1 does

P1.1 can export one deterministic JSON package derived only from:

- the clean Git repository identity;
- the current V5 autonomy constitution;
- the current Mission 103 governance contract; and
- byte identities for a short allowlist of already-public documentation.

The package contains `projection.json` and `manifest.json`. The manifest binds the exact projection bytes by SHA-256, and the verifier can rebuild the projection from the current clean repository and require exact parity.

The first projection intentionally contains no timestamps. For the same clean repository state, its bytes are deterministic.

## What P1.1 cannot read

P1.1 does not open:

- the Mission 100 acquisition database;
- Mission 101 authority state;
- the Mission 103 governance database;
- raw market payloads;
- protected replication, validation, or holdout values;
- founder authorization nonces;
- credentials, API keys, or environment secrets.

It makes no network request and has no arbitrary-path input for projection sources.

A later, separately reviewed P1 metadata bridge may expose a tightly enumerated set of private-runtime health metadata. That capability is not part of this contract.

## Authority

The projection has authority effect `NONE`.

It does not authorize research execution, validation or holdout opening, ML, paper trading, live trading, exchange or broker access, credentials, signed requests, orders, portfolio allocation, or capital.

The public web application will be a consumer of projection evidence. It will not become authoritative DeltaGrid state.

## Output boundary

Exports must go to an absolute directory outside the Git checkout. Any symbolic-link component in the destination path fails closed; operators that intentionally start from an alias must first resolve it to a physical path. Non-empty existing destinations and output-file collisions also fail closed. Files are written exclusively rather than overwritten.

The exporter does not upload or publish the package. Network publication belongs to the separate web product and will be reviewed independently.

## Operator commands

After P1.1 is merged and the repository is clean:

```text
python -m offchain.public_projection show-contract
python -m offchain.public_projection export --destination /absolute/outside/repository/path
python -m offchain.public_projection verify --path /absolute/outside/repository/path
```

The normal full DeltaGrid test suite remains required before publication of P1.1.
