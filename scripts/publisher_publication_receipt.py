"""Record publication privately only after checking the deployed catalog."""
import json
import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen


def verified(manifest, catalog, slug, revision):
    return (manifest.get('target') == 'cloudflare-pages'
            and manifest.get('revision') == revision
            and isinstance(catalog, list)
            and any(show.get('slug') == slug for show in catalog))


def main():
    issue = json.loads(Path('issue.json').read_text(encoding='utf-8'))
    marker = re.match(r'^<!-- torahpod-request:([0-9a-f-]{36}) -->\r?\n<!-- torahpod-account:(\{[^\n]+\}) -->', issue.get('body', ''))
    if not marker:
        return
    account = json.loads(marker.group(2))
    if account.get('environment') != 'production' or account.get('kind') != 'submission':
        raise RuntimeError('Unsupported approval request')
    slug, revision = os.environ['SHOW_SLUG'], os.environ['DEPLOYMENT_REVISION']
    if not re.fullmatch(r'[a-z0-9-]{1,80}', slug) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Invalid publication receipt')
    origin = 'https://torah-pod.pages.dev'
    for attempt in range(12):
        try:
            values = []
            for name in ('deployment.json', 'catalog.json'):
                request = Request(f'{origin}/{name}?verification={revision}', headers={'Cache-Control': 'no-cache'})
                with urlopen(request, timeout=20) as response:
                    values.append(json.load(response))
            if verified(*values, slug, revision):
                break
        except (OSError, ValueError):
            pass
        if attempt == 11:
            raise RuntimeError('Deployment is not verified; publication status remains pending')
        time.sleep(10)
    receipt = {'requestId': marker.group(1), 'showSlug': slug, 'deploymentRevision': revision}
    body = '<!-- torahpod-publication:' + json.dumps(receipt, separators=(',', ':')) + ' -->'
    repo = os.environ['ISSUE_REPO']
    if repo != 'shaqo88/torah-pod-intake':
        raise RuntimeError('Publication receipts must remain private')
    request = Request(f'https://api.github.com/repos/{repo}/issues/{issue["number"]}/comments',
                      data=json.dumps({'body': body}).encode(),
                      headers={'Authorization': 'Bearer ' + os.environ['ONBOARDING_INTAKE_TOKEN'],
                               'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json'}, method='POST')
    with urlopen(request, timeout=20):
        pass
    print('Verified publisher publication recorded privately')


if __name__ == '__main__':
    main()
