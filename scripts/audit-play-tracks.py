"""Report known Play track releases using only GET requests."""

import json
import os

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials


PACKAGE = "com.torahpod.app"
API = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE}/tracks"
KNOWN_TRACKS = ("internal", "production", "alpha", "beta")


def main():
    credentials = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )
    session = AuthorizedSession(credentials)
    for track in KNOWN_TRACKS:
        response = session.get(f"{API}/{track}/releases", timeout=30)
        if response.status_code == 404:
            if track == "internal":
                raise ValueError("Could not find the known internal release (HTTP 404)")
            print(json.dumps({"track": track, "result": "not found or unavailable"}))
            continue
        if response.status_code != 200:
            raise ValueError(f"Could not list {track} releases (HTTP {response.status_code})")
        releases = [
            {
                "versionCodes": [artifact["versionCode"] for artifact in release.get("activeArtifacts", [])],
                "state": release.get("releaseLifecycleState"),
            }
            for release in response.json().get("releases", [])
        ]
        print(json.dumps({"track": track, "releases": releases}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # OAuth and HTTP exceptions may contain credential-bearing details.
        message = str(error) if isinstance(error, ValueError) and str(error).startswith("Could not ") else type(error).__name__
        raise SystemExit(f"Play track audit failed: {message}") from None
