# Onboarding Worker

Cloudflare Worker used by the public onboarding form. It validates bounded
request data and creates a record in the private review system while returning
only a generic response to the browser.

Run its tests from the repository root:

```bash
node --test workers/onboarding/test/submit.test.mjs
```

Deployment, token scopes, private labels, rotation, and recovery procedures are
maintained only in the private operations repository.
