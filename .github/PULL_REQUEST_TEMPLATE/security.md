## What changed

<!-- Summary of the security fix or hardening. -->

## Threat description

<!-- What could an attacker/unauthorized user do before this change? -->

## Blast radius

<!-- What data/tenants/users were exposed, and for how long. -->

## Disclosure handling

<!-- Was this reported externally? Does it need coordinated disclosure or user notification? -->

## Linked issue

Closes #

## Risk and rollback

<!-- Required for every security PR. -->

## Checklist

- [ ] Regression test added proving the vulnerability is closed
- [ ] Two approvals obtained if this touches auth, tenant isolation, or migrations (CODEOWNERS)
- [ ] No secrets, `.env` files, or generated documents committed
- [ ] README.md / SECURITY notes updated if relevant
