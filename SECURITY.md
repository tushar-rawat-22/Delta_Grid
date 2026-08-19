# Security

DeltaGrid includes a public observer, an authenticated founder gateway, research tooling, and release automation. If you find a security problem, please report it privately rather than opening a public issue with exploit details.

## Reporting a vulnerability

Email **tushar142004@gmail.com** with:

- the affected route, file, workflow, or component;
- what you observed and why you think it is a security issue;
- the minimum steps needed to reproduce it;
- any relevant request/response details with secrets, tokens, personal data, and private research content removed; and
- the practical impact you believe is possible.

Please do not include credentials, session cookies, Cloudflare Access tokens, API keys, founder research records, protected evidence, or other private material in the report.

## What is in scope

Useful reports include problems that could expose or weaken:

- the separation between the public observer and founder-only surfaces;
- authentication or founder-identity enforcement;
- private API or research data isolation;
- release, rollback, CI, or dependency-security controls;
- secret handling or credential scope;
- path, filesystem, request-validation, or injection boundaries; or
- a security assumption documented in the repository that no longer holds.

The public repository intentionally contains control code, documentation, deterministic fixtures, and sanitized demonstration material. A report that only notes that the repository is public is not a vulnerability.

## Testing boundaries

Please keep testing non-destructive. Do not attempt to obtain another person's credentials, bypass third-party accounts, access private founder data, degrade availability, create excessive traffic, alter hosted state, or test against exchanges, brokers, or financial accounts.

The project does not authorize paper trading, live trading, exchange access, orders, or capital deployment. Security testing should not cross those boundaries.

## Response

I will first confirm receipt and assess whether the report affects a live boundary or only repository code. Confirmed issues will be fixed through the normal reviewed branch, test, CI, and release process. Public disclosure should wait until the issue is resolved or we have agreed on a safe disclosure point.

There is currently no paid bug-bounty programme.
