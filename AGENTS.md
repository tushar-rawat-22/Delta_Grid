# DeltaGrid contributor instructions

DeltaGrid is a single-tenant quantitative research and engineering repository.
Use `offchain/.venv/bin/python` for Python work. The standard full suite is:

```bash
env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 \
offchain/.venv/bin/python -m pytest -p no:cacheprovider offchain/tests -q
```

Do not install or upgrade dependencies without founder approval. Inspect the
current contracts before editing. No network, exchange, credential, order,
capital, paper-trading, or live-trading action is permitted unless an explicit
current contract authorizes that exact action. Preserve historical evidence and
never read or print secret values. Use temporary directories for tests.

Keep public prose natural and technically specific, and update
`docs/documentation-status.json` when the documentation inventory changes. Do
not commit, push, create a pull request, or change repository settings unless
the founder explicitly asks. Fail closed whenever authority is unclear.
