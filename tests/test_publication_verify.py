import io
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from podcast_feeds import publication_verify
from podcast_feeds.publication_verify import verify_target


REVISION = "a" * 40


class PublicationTargetVerificationTests(unittest.TestCase):
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
