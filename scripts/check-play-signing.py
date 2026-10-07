"""Read Play-signed APK certificates without changing any release track."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

PACKAGE = "com.torahpod.app"
API = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE}"


def select_download(group):
    universal = group.get("generatedUniversalApk", {})
    if universal.get("downloadId"):
        return universal["downloadId"]
    for apk in group.get("generatedSplitApks", []):
        if apk.get("moduleName") == "base" and not apk.get("splitId") and apk.get("downloadId"):
            return apk["downloadId"]
    raise ValueError("Play did not provide a universal or base APK")


def certificate_digests(output, expected_sha256):
    values = {}
    for kind, length in [("SHA-1", 40), ("SHA-256", 64)]:
        matches = re.findall(rf"^Signer #\d+ certificate {kind} digest: ([0-9a-fA-F]+)$", output, re.MULTILINE)
        if len(matches) != 1 or len(matches[0]) != length:
            raise ValueError("Expected exactly one verified APK signer")
        values[kind.replace("-", "").lower()] = matches[0].upper()
    if values["sha256"] != expected_sha256.replace(":", "").upper():
        raise ValueError("Downloaded APK certificate differs from Play metadata")
    return values


def main():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-code", type=int, required=True)
    parser.add_argument("--apksigner", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/androidpublisher"])
    session = AuthorizedSession(credentials)
    base = f"{API}/generatedApks/{args.version_code}"
    response = session.get(base, timeout=60)
    if response.status_code != 200:
        raise ValueError(f"Play APK listing failed (HTTP {response.status_code})")
    groups = response.json().get("generatedApks", [])
    if not groups:
        raise ValueError("No Play-signed APKs were returned")
    certificates = []
    with tempfile.TemporaryDirectory() as directory:
        for group in groups:
            download_id = quote(select_download(group), safe="")
            download = session.get(f"{base}/downloads/{download_id}:download", params={"alt": "media"}, timeout=120, stream=True)
            if download.status_code != 200:
                raise ValueError(f"Play APK download failed (HTTP {download.status_code})")
            apk = Path(directory) / "play-signed.apk"
            with apk.open("wb") as handle:
                for chunk in download.iter_content(1024 * 1024):
                    handle.write(chunk)
            download.close()
            result = subprocess.run([args.apksigner, "verify", "--print-certs", str(apk)], capture_output=True, text=True, check=False)
            if result.returncode:
                raise ValueError("Play APK signature verification failed")
            digests = certificate_digests(result.stdout, group["certificateSha256Hash"])
            if digests not in certificates:
                certificates.append(digests)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"packageName": PACKAGE, "versionCode": args.version_code, "certificates": certificates}, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(certificates)} Play app-signing certificate(s) for version {args.version_code}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # OAuth/library exceptions can include credential contents; only our
        # deliberately sanitized validation messages are safe for CI logs.
        message = str(error) if isinstance(error, ValueError) and str(error).startswith(("Play ", "No Play-", "Expected exactly", "Downloaded APK")) else type(error).__name__
        raise SystemExit(f"Play signing verification failed: {message}") from None
