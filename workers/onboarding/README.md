# Onboarding Worker

Cloudflare Worker that receives the public onboarding form and creates a
GitHub issue for maintainer approval.

## Required Secrets

Worker secret:

- `GITHUB_TOKEN`: fine-grained GitHub token with access to this repo and
  `Issues: Read and write`.

GitHub Actions secrets for deploy:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `ONBOARDING_GITHUB_TOKEN`

`CLOUDFLARE_ACCOUNT_ID` can be the same account ID used for R2.
`CLOUDFLARE_API_TOKEN` needs permission to edit Workers scripts.

## Deploy

After adding the GitHub Actions secrets, run:

```text
Actions -> Deploy Onboarding Worker -> Run workflow
```

The deploy prints the `workers.dev` URL. Set the repo variable
`ONBOARDING_WORKER_ENDPOINT` to that URL, then rerun the GitHub Pages workflow.
