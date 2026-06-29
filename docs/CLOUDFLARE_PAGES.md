# Cloudflare Pages Deployment

The static Torah Pod site is already deployed by GitHub Pages.

Cloudflare Pages is prepared as an optional next hosting target:

```text
https://torah-pod.pages.dev
```

The workflow is manual-only for now:

```text
Actions -> Deploy Cloudflare Pages -> Run workflow
```

## Required Cloudflare setup

The repository already has `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`
secrets for the onboarding Worker. The current token can authenticate to the
account, but it failed to deploy Pages with:

```text
Authentication error [code: 10000]
```

Create or update the GitHub Actions secret `CLOUDFLARE_API_TOKEN` so it can
manage Cloudflare Pages for the account. The token needs Pages edit/deploy
permission for the account that owns the project.

After that, run the workflow manually. It will create or reuse the `torah-pod`
Pages project and deploy the checked-in `public/` directory.

## Onboarding Worker CORS

`workers/onboarding/wrangler.toml` already allows both origins:

```text
https://shaqo88.github.io
https://torah-pod.pages.dev
```

After the Cloudflare token is updated, redeploy the onboarding Worker too:

```text
Actions -> Deploy Onboarding Worker -> Run workflow
```
