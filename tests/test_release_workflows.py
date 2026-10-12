from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from podcast_feeds.deployment_manifest import build_manifest


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


class ReleaseWorkflowTests(unittest.TestCase):
    def test_targets_fetch_same_release_before_their_final_preflight(self):
        for filename, target in (("cloudflare_pages.yml", "cloudflare-pages"), ("pages.yml", "github-pages")):
            with self.subTest(filename=filename):
                workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
                self.assertEqual(workflow["concurrency"]["queue"], "max")
                self.assertFalse(workflow["concurrency"]["cancel-in-progress"])
                steps = workflow["jobs"]["deploy"]["steps"]
                names = [step.get("name") for step in steps]
                fetch = steps[names.index("Fetch and verify retained release")]
                legacy = steps[names.index("Prepare legacy public site")]
                receipt = steps[names.index("Add target-specific deployment receipt")]
                self.assertIn("release_pipeline fetch", fetch["run"])
                self.assertIn("--release-id \"$RELEASE_ID\"", fetch["run"])
                self.assertIn("release_id != ''", fetch["if"])
                self.assertIn("release_id == ''", legacy["if"])
                self.assertIn("deployment_manifest", receipt["run"])
                self.assertLess(names.index("Fetch and verify retained release"), names.index("Check main again immediately before deployment"))
                self.assertLess(names.index("Check main again immediately before deployment"), names.index("Verify exact live revision"))
                verify = steps[names.index("Verify exact live revision")]
                self.assertIn("--payload-digest", verify["run"])
                self.assertIn(target, verify["run"])

    def test_writers_capture_inputs_before_strict_render_and_keep_legacy_gate(self):
        for filename in ("build.yml", "discover_platform_links.yml", "sync_publish.yml"):
            with self.subTest(filename=filename):
                workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
                job = workflow["jobs"].get("build") or workflow["jobs"].get("discover") or workflow["jobs"].get("publish")
                steps = job["steps"]
                names = [step.get("name") for step in steps]
                self.assertLess(names.index("Capture linked-feed inputs for retained release"), names.index("Retain validated release"))
                self.assertIn("vars.RELEASE_ARTIFACTS_ENABLED == 'true'", steps[names.index("Retain validated release")]["if"])
                self.assertIn("TORAH_POD_RELEASE_RENDER", str(steps))

    def test_target_metadata_adds_artifact_identity_without_changing_legacy_receipt(self):
        revision = "a" * 40
        old = build_manifest(target="github-pages", revision=revision, run_id="1")
        self.assertNotIn("release_id", old)
        new = build_manifest(target="github-pages", revision=revision, run_id="1",
                             release_id="b" * 64, payload_digest="c" * 64)
        self.assertEqual(new["revision"], old["revision"])
        self.assertEqual((new["release_id"], new["payload_digest"]), ("b" * 64, "c" * 64))
        with self.assertRaises(ValueError):
            build_manifest(target="github-pages", revision=revision, run_id="1", release_id="b" * 64)


if __name__ == "__main__":
    unittest.main()
