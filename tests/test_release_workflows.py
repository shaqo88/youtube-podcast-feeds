from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from podcast_feeds.deployment_manifest import build_manifest


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


class ReleaseWorkflowTests(unittest.TestCase):
    def test_committed_release_path_requires_current_main_and_exact_public_bytes(self):
        workflow = yaml.safe_load((WORKFLOWS / "publish_committed_release.yml").read_text(encoding="utf-8"))
        self.assertEqual(workflow[True].keys(), {"workflow_dispatch", "workflow_run"})
        self.assertTrue(workflow[True]["workflow_dispatch"]["inputs"]["revision"]["required"])
        self.assertEqual(workflow["concurrency"]["group"], "publish-committed-release")
        steps = workflow["jobs"]["publish"]["steps"]
        by_name = {step.get("name"): step for step in steps if step.get("name")}
        guard = by_name["Require exact current main and artifact mode"]["run"]
        self.assertIn('"$ARTIFACT_MODE" != "true"', guard)
        self.assertIn('"$(git rev-parse origin/main)" != "$REVISION"', guard)
        verify = by_name["Verify committed public bytes"]["run"]
        self.assertIn("python -m podcast_feeds.build", verify)
        self.assertIn("git status --porcelain -- public", verify)
        self.assertIn("python -m podcast_feeds.validate", verify)
        self.assertIn("release_pipeline prepare", by_name["Retain exact committed release"]["run"])
        self.assertIn("--release-id \"$RELEASE_ID\"", by_name["Hand retained release to both targets"]["run"])
        self.assertFalse(any("git push" in step.get("run", "") for step in steps))

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
        for filename in ("build.yml", "discover_platform_links.yml", "sync_publish.yml", "migrate_media.yml"):
            with self.subTest(filename=filename):
                workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
                job = (workflow["jobs"].get("build") or workflow["jobs"].get("discover")
                       or workflow["jobs"].get("publish") or workflow["jobs"].get("migrate"))
                steps = job["steps"]
                names = [step.get("name") for step in steps]
                self.assertLess(names.index("Capture linked-feed inputs for retained release"), names.index("Retain validated release"))
                self.assertIn("vars.RELEASE_ARTIFACTS_ENABLED == 'true'", steps[names.index("Retain validated release")]["if"])
                self.assertIn("TORAH_POD_RELEASE_RENDER", str(steps))

    def test_empty_rebuild_and_discovery_do_not_retain_or_dispatch(self):
        for filename in ("build.yml", "discover_platform_links.yml"):
            with self.subTest(filename=filename):
                workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
                job = next(value for value in workflow["jobs"].values() if any(
                    step.get("name") == "Commit rebuilt feeds" or step.get("name") == "Commit platform link updates"
                    for step in value.get("steps", [])
                ))
                steps = job["steps"]
                commit = next(step for step in steps if step.get("id") == "commit")
                retain = next(step for step in steps if step.get("name") == "Retain validated release")
                handoff = next(step for step in steps if step.get("name") == "Hand validated content to deployment")
                self.assertIn("git diff --staged --quiet", commit["run"])
                self.assertIn("echo 'changed=true'", commit["run"])
                self.assertIn("steps.commit.outputs.changed == 'true'", retain["if"])
                self.assertIn("steps.commit.outputs.changed == 'true'", handoff["if"])

    def test_legacy_direct_writers_cannot_bypass_artifact_target_ordering(self):
        for filename in ("sync.yml", "approve_onboarding.yml"):
            with self.subTest(filename=filename):
                workflow = yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))
                jobs = workflow["jobs"]
                job = jobs.get("sync") or jobs.get("onboard") or jobs.get("approve")
                if job is None:
                    job = next(value for value in jobs.values() if any(
                        step.get("name") == "Retain validated release" for step in value.get("steps", [])
                    ))
                steps = job["steps"]
                names = [step.get("name") for step in steps]
                self.assertLess(names.index("Capture linked-feed inputs for retained release"),
                                names.index("Retain validated release"))
                self.assertLess(names.index("Retain validated release"),
                                names.index("Hand retained release to deployment"))
                handoff = steps[names.index("Hand retained release to deployment")]
                self.assertIn("--release-id \"$RELEASE_ID\"", handoff["run"])
                self.assertIn("RELEASE_ARTIFACTS_ENABLED == 'true'", handoff["if"])
                for step in steps:
                    if step.get("name") in {"Prepare public site", "Deploy Cloudflare Pages"} or step.get("id") in {
                        "deployment", "deployment_retry",
                    }:
                        self.assertIn("RELEASE_ARTIFACTS_ENABLED != 'true'", step["if"])
                self.assertIn("Fail incomplete retained release", names)

    def test_empty_hourly_sync_skips_retained_publication(self):
        workflow = yaml.safe_load((WORKFLOWS / "sync.yml").read_text(encoding="utf-8"))
        job = next(value for value in workflow["jobs"].values() if any(
            step.get("name") == "Commit successful sync" for step in value.get("steps", [])
        ))
        steps = job["steps"]
        commit = next(step for step in steps if step.get("id") == "commit")
        self.assertIn("git diff --staged --quiet", commit["run"])
        self.assertIn("echo 'changed=true'", commit["run"])
        for name in ("Retain validated release", "Hand retained release to deployment",
                     "Verify retained release on GitHub Pages", "Verify retained release on Cloudflare Pages"):
            step = next(step for step in steps if step.get("name") == name)
            self.assertIn("steps.commit.outputs.changed == 'true'", step["if"])

    def test_media_migration_hands_exact_retained_release_and_keeps_dry_run_legacy_behavior(self):
        workflow = yaml.safe_load((WORKFLOWS / "migrate_media.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["migrate"]["steps"]
        by_name = {step.get("name"): step for step in steps if step.get("name")}
        self.assertIn("inputs.dry_run == 'false'", by_name["Retain validated release"]["if"])
        self.assertIn("release_pipeline prepare", by_name["Retain validated release"]["run"])
        self.assertIn("--release-id", by_name["Hand validated content to deployment"]["run"])
        self.assertIn("RELEASE_ID", by_name["Hand validated content to deployment"]["env"])
        self.assertIn('git add "shows/${{ inputs.show }}" public', by_name["Commit migrated media records"]["run"])
        self.assertIn('git add "shows/${{ inputs.show }}" "public/${{ inputs.show }}"',
                      by_name["Commit migrated media records"]["run"])
        self.assertEqual(workflow[True]["workflow_dispatch"]["inputs"]["dry_run"]["default"], "true")

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
