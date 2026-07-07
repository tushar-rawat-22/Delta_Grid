# ADR-0002: Git Commit Discipline and Selective Staging

## Status

Accepted

## Date

2026-07-07

---

## Context

DeltaGrid is being developed alongside SkillMint on the same Mac.

The project must avoid:

- accidental cross-project changes
- accidental .env commits
- accidental .venv commits
- accidental database commits
- messy commit history
- unclear rollback points
- mixed commits

---

## Decision

Use:

- atomic commits
- descriptive commit messages
- selective staging

Avoid:

    git add .

---

## Actual Commit Examples

Smart contract foundation:

    git commit -m "Complete DeltaGrid smart contract foundation"

Offchain monitor:

    git commit -m "Add safe offchain chain monitor"

---

## Actual Selective Staging Used

    git add offchain/indexer/chain_monitor.py offchain/config/.env.example offchain/requirements.txt

Commit result:

    [master 571044c] Add safe offchain chain monitor
    3 files changed, 155 insertions(+)
    create mode 100644 offchain/config/.env.example
    create mode 100644 offchain/indexer/chain_monitor.py
    create mode 100644 offchain/requirements.txt

---

## Git Ritual

Before staging:

    git status

Stage only required files:

    git add path/to/file1 path/to/file2

Commit:

    git commit -m "Verb specific-module purpose"

Verify:

    git status

Expected final state:

    nothing to commit, working tree clean

---

## Commit Message Convention

Format:

    Verb + module + purpose

Good:

    git commit -m "Add risk scoring simulator"
    git commit -m "Document offchain environment setup"
    git commit -m "Add pool reserve indexer"
    git commit -m "Fix stale oracle test underflow"

Bad:

    git commit -m "update"
    git commit -m "changes"
    git commit -m "final"
    git commit -m "done"

---

## Reasoning

Selective staging prevents accidental commits of:

- .env
- .venv
- SQLite databases
- logs
- caches
- generated outputs
- private keys
- unrelated experiments

Atomic commits make rollback easier.

---

## Commit Checklist

Before each commit:

- Does this change belong to DeltaGrid?
- Is this one focused change?
- Did I avoid .env?
- Did I avoid .venv?
- Did I avoid database files?
- Did I avoid logs?
- Did I avoid private keys?
- Is the message clear?
- Can this be rolled back safely?

---

## Review Trigger

Review this ADR when adding:

- GitHub remote
- branches
- CI/CD
- collaborators
- deployment automation
- release tags
