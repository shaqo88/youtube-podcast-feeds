import io
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import yaml

from podcast_feeds import publication_verify
from podcast_feeds.publication_verify import verify_target


REVISION = "a" * 40


class PublicationTargetVerificationTests(unittest.TestCase):
    def test_cloudflare_window_covers_observed_delayed_deployment(self):
        self.assertIsNone(inspect.signature(verify_target).parameters["attempts"].default)
        attempted = []
        old = {"target": "cloudflare-pages", "revision": "b" * 40}
        current = {"target": "cloudflare-pages", "revision": REVISION}
        self.assertTrue(verify_target(
            "cloudflare-pages", REVISION, [],
            read=lambda _, attempt: attempted.append(attempt) or (old if attempt <= 18 else current),
            pause=lambda _: None,
        ))
        self.assertEqual(attempted, list(range(1, 20)))

    def test_mirror_window_covers_deployment_after_dispatch(self):
        attempts = []
        receipt = {"target": "github-pages", "revision": REVISION}
        self.assertTrue(verify_target(
            "github-pages", REVISION, [],
            read=lambda _, attempt: attempts.append(attempt) or ({} if attempt <= 20 else receipt),
            pause=lambda _: None,
        ))
        self.assertEqual(attempts, list(range(1, 22)))

    def test_stale_receipt_and_transient_http_error_remain_bounded(self):
        attempted = []
        error = HTTPError("https://example.test/deployment.json", 503, "Unavailable", {}, None)
        def read(_target, attempt):
            attempted.append(attempt)
            if attempt == 2:
                raise error
            return {"target": "cloudflare-pages", "revision": "b" * 40}
        self.assertFalse(verify_target(
            "cloudflare-pages", REVISION, [], read=read,
            attempts=3, pause=lambda _: None,
        ))
        self.assertEqual(attempted, [1, 2, 3])

    def test_superseded_revision_never_verifies_original(self):
        newer = {"target": "cloudflare-pages", "revision": "f" * 40,
                 "release_id": "e" * 64, "payload_digest": "d" * 64}
        self.assertFalse(verify_target(
            "cloudflare-pages", REVISION, [], read=lambda *_: newer,
            attempts=2, pause=lambda _: None,
            release_id="b" * 64, payload_digest="c" * 64,
        ))

    def test_artifact_mode_requires_both_exact_receipt_digests(self):
        release_id = "b" * 64
        payload_digest = "c" * 64
        receipt = {"target": "github-pages", "revision": REVISION,
                   "release_id": release_id, "payload_digest": payload_digest}
        self.assertTrue(verify_target("github-pages", REVISION, [], read=lambda *_: receipt,
                                      release_id=release_id, payload_digest=payload_digest, attempts=1))
        self.assertFalse(verify_target("github-pages", REVISION, [], read=lambda *_: {**receipt, "payload_digest": "d" * 64},
                                       release_id=release_id, payload_digest=payload_digest, attempts=1))
        self.assertFalse(verify_target("github-pages", REVISION, [], read=lambda *_: {"target": "github-pages", "revision": REVISION},
                                       release_id=release_id, payload_digest=payload_digest, attempts=1))

    def test_receipt_request_uses_project_user_agent(self):
        response = io.BytesIO(b'{"target":"cloudflare-pages","revision":"' + b"a" * 40 + b'"}')
        with patch.object(publication_verify, "urlopen", return_value=response) as open_url:
            self.assertEqual(publication_verify.read_deployment("cloudflare-pages", 1)["revision"], REVISION)
        self.assertEqual(open_url.call_args.args[0].get_header("User-agent"), "torah-pod-publication/1.0")

    def test_publisher_records_each_target_and_guards_notification(self):
        workflow = yaml.safe_load(Path(".github/workflows/sync_publish.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["publish"]["steps"]
        by_name = {step.get("name"): step for step in steps}
        primary = by_name["Verify primary production feed"]
        mirror = by_name["Verify mirror deployment"]
        self.assertTrue(primary["continue-on-error"])
        self.assertTrue(mirror["continue-on-error"])
        self.assertIn("--target cloudflare-pages", primary["run"])
        self.assertIn("--target github-pages", mirror["run"])
        self.assertIn("timeout 21m python -m podcast_feeds.publication_verify", mirror["run"])
        legacy = yaml.safe_load(Path(".github/workflows/sync.yml").read_text(encoding="utf-8"))
        legacy_mirror = next(
            step for step in legacy["jobs"]["sync"]["steps"]
            if step.get("name") == "Verify retained release on GitHub Pages"
        )
        self.assertIn("timeout 21m python -m podcast_feeds.deployment_handoff verify", legacy_mirror["run"])
        self.assertIn("--attempts 120", legacy_mirror["run"])
        self.assertIn("steps.verify_primary.outcome", by_name["Record primary deployment outcome"]["run"])
        self.assertIn("steps.verify_mirror.outcome", by_name["Record mirror deployment outcome"]["run"])
        self.assertIn("steps.verify_primary.outcome == 'success'", by_name["Prepare new episode notification"]["if"])
        self.assertIn("steps.verify_mirror.outcome == 'success'", by_name["Prepare new episode notification"]["if"])
        self.assertIn("steps.notification.outcome == 'success'", by_name["Record that no notification was required"]["if"])

    def test_primary_success_and_mirror_failure_are_independent(self):
        primary = verify_target(
            "cloudflare-pages", REVISION, ["show"],
            read=lambda target, attempt: {"target": target, "revision": REVISION},
            validate=lambda show: True, attempts=1,
        )
        mirror = verify_target(
            "github-pages", REVISION, ["show"],
            read=lambda target, attempt: {"target": target, "revision": "b" * 40},
            attempts=1,
        )
        self.assertTrue(primary)
        self.assertFalse(mirror)

    def test_wrong_target_or_revision_never_verifies(self):
        for observed in (
            {"target": "github-pages", "revision": REVISION},
            {"target": "cloudflare-pages", "revision": "b" * 40},
            [],
        ):
            with self.subTest(observed=observed):
                self.assertFalse(verify_target(
                    "cloudflare-pages", REVISION, [],
                    read=lambda target, attempt: observed, attempts=1,
                ))

    def test_transient_error_retries_and_primary_requires_feed_validation(self):
        reads = iter((OSError("offline"), {"target": "cloudflare-pages", "revision": REVISION}))
        validations = []
        read_attempts = []

        def read(target, attempt):
            read_attempts.append(attempt)
            result = next(reads)
            if isinstance(result, Exception):
                raise result
            return result

        self.assertTrue(verify_target(
            "cloudflare-pages", REVISION, ["one"], read=read,
            validate=lambda show: validations.append(show) or True,
            attempts=2, delay=0, pause=lambda _: None,
        ))
        self.assertEqual(validations, ["one"])
        self.assertEqual(read_attempts, [1, 2])

        self.assertFalse(verify_target(
            "cloudflare-pages", REVISION, ["one"],
            read=lambda target, attempt: {"target": target, "revision": REVISION},
            validate=lambda show: False, attempts=1,
        ))


if __name__ == "__main__":
    unittest.main()
