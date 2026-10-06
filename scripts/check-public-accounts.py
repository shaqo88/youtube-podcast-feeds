"""Validate that deployed static files use the selected public account config."""
import json
import os
from pathlib import Path

environment = os.environ.get('ACCOUNTS_ENVIRONMENT', 'production')
if environment not in ('preview', 'production'):
    raise SystemExit('Invalid account environment')
expected = json.loads(Path(f'config/accounts.{environment}.json').read_text())
actual = json.loads(Path('public/accounts-config.json').read_text())
if actual != expected:
    raise SystemExit('Build the public site with the selected account environment before deploying')
for name in ('storage.js', 'accounts-bootstrap.js', 'accounts.mjs', 'accounts-core.mjs', 'firebase-auth.bundle.js'):
    expected_source=Path(f'podcast_feeds/web/{name}').read_text(encoding='utf-8')
    if name.endswith('.mjs'):
        expected_source=expected_source.replace("'./accounts-core.mjs'", "'./accounts-core.js'")
    if Path(f'public/assets/{name.replace(".mjs", ".js")}').read_text(encoding='utf-8') != expected_source:
        raise SystemExit(f'Rebuild the public application: {name} differs from source')
print('Public account configuration and assets verified')
