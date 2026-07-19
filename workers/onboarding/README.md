# Onboarding Worker

Cloudflare Worker that receives the public onboarding form and creates a
private GitHub issue for maintainer approval.

## Required Secrets

Worker secret:

- `GITHUB_TOKEN`: fine-grained GitHub token with `Issues: Read and write` on
  `shaqo88/torah-pod-intake` and read access to
  `shaqo88/youtube-podcast-feeds` for duplicate detection.

GitHub Actions secrets for deploy:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `ONBOARDING_INTAKE_TOKEN`

`CLOUDFLARE_ACCOUNT_ID` can be the same account ID used for R2.
`CLOUDFLARE_API_TOKEN` needs permission to edit Workers scripts.

## Deploy

After adding the GitHub Actions secrets, run:

```text
Actions -> Deploy Onboarding Worker -> Run workflow
```

The deploy prints the `workers.dev` URL. Set the repo variable
`ONBOARDING_WORKER_ENDPOINT` to that URL, then rerun the GitHub Pages workflow.
