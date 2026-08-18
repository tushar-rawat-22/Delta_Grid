# M101 binding planner usage

After a Founder preregistration handoff has passed trusted-local V2 verification, run:

```bash
cd web
npm run plan:m101-binding -- /absolute/path/to/founder-prereg-handoff-<sha256>.json
```

Successful output is canonical JSON with schema `DELTAGRID_M101_HANDOFF_BINDING_PLAN_V1`. It identifies the declared provider, instrument, benchmark, stream and interval, lists still-unresolved trusted-local facts, and orders the later canonical resolution steps. It never performs those steps.
