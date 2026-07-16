# Repository Instructions

- For all GitHub CLI operations in this repository, use the existing `shaqo88` authentication entry without changing the machine's global active `gh` account.
- Use a command-scoped token, then remove it after the operation:

```powershell
$env:GH_TOKEN = gh auth token --user shaqo88
try {
  gh <command>
} finally {
  Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
}
```

- Do not run `gh auth switch`, `gh auth login`, or edit global GitHub CLI configuration to make `shaqo88` active.
