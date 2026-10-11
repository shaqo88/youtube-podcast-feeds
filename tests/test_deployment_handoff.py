import os
import io
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import yaml

from podcast_feeds import deployment_handoff as handoff


@contextmanager
def fixture_repository():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(dir=previous) as directory:
        os.chdir(directory)
        try:
            def git(*args):
                return subprocess.check_output(["git", *args], text=True).strip()

            git("init", "-q", "-b", "main")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            Path("public").mkdir()
            Path("public/feed.xml").write_text("first", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "first")
            first = git("rev-parse", "HEAD")
            Path("source.txt").write_text("different source", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "same public bytes")
            same_public = git("rev-parse", "HEAD")
            Path("public/feed.xml").write_text("corrected", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "corrected feed")
            corrected = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/origin/main", corrected)
            yield first, same_public, corrected
        finally:
            os.chdir(previous)


class DeploymentHandoffTests(unittest.TestCase):
    def test_delayed_dispatch_cannot_cancel_or_replace_newer_deployment(self):
        """An older event can arrive after a newer revision is queued.

        Both runs must reach preflight in serial order. The older run then
        observes either newer main content or a newer live receipt and skips.
        """
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                concurrency = workflow["concurrency"]
                self.assertFalse(concurrency.get("cancel-in-progress", False))
                self.assertEqual(concurrency.get("queue"), "max")

    def test_deployment_success_requires_exact_live_receipt(self):
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                steps = workflow["jobs"]["deploy"]["steps"]
                verification = [step for step in steps if step.get("name") == "Verify exact live revision"]
                self.assertEqual(len(verification), 1)
                self.assertIn("deployment_handoff verify", verification[0]["run"])
                self.assertIn("$(git rev-parse HEAD)", verification[0]["run"])

        revision = "a" * 40
        with patch.object(handoff, "live_revision", side_effect=[None, "b" * 40, revision]), patch.object(
            handoff.time, "sleep"
        ) as sleep:
            self.assertEqual(handoff.verify(revision, "github-pages", attempts=3, delay_seconds=0), 0)
            self.assertEqual(sleep.call_count, 2)
        with patch.object(handoff, "live_revision", return_value="b" * 40), patch.object(
            handoff.time, "sleep"
        ) as sleep:
            self.assertEqual(handoff.verify(revision, "github-pages", attempts=2, delay_seconds=0), 1)
            self.assertEqual(sleep.call_count, 1)

    def test_main_is_rechecked_after_preparation_before_target_mutation(self):
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                steps = workflow["jobs"]["deploy"]["steps"]
                first = next(i for i, step in enumerate(steps) if step.get("id") == "handoff")
                prepared = next(i for i, step in enumerate(steps) if step.get("name") == "Prepare public site")
                latest = next(i for i, step in enumerate(steps) if step.get("id") == "latest")
                deploy = next(
                    i for i, step in enumerate(steps)
                    if step.get("name") == "Deploy public site" or step.get("id") == "deployment"
                )
                self.assertLess(first, prepared)
                self.assertLess(prepared, latest)
                self.assertLess(latest, deploy)
                self.assertIn("deployment_handoff preflight", steps[latest]["run"])
                self.assertIn("steps.latest.outputs.deploy == 'true'", steps[deploy]["if"])

    def test_workflows_dispatch_after_validation_and_deploy_exact_revision(self):
        for name in ("discover_platform_links.yml", "build.yml", "migrate_media.yml"):
            with self.subTest(writer=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                self.assertEqual(workflow["permissions"]["actions"], "write")
                steps = next(iter(workflow["jobs"].values()))["steps"]
                checkout = next(step for step in steps if "actions/checkout@" in step.get("uses", ""))
                self.assertEqual(checkout["with"]["fetch-depth"], 0)
                validation = next(i for i, step in enumerate(steps) if step.get("name", "").startswith("Validate"))
                commit = next(i for i, step in enumerate(steps) if step.get("name", "").startswith("Commit"))
                dispatch = next(i for i, step in enumerate(steps) if step.get("name") == "Hand validated content to deployment")
                self.assertLess(validation, commit)
                self.assertLess(commit, dispatch)
                self.assertIn("deployment_handoff dispatch", steps[dispatch]["run"])
                self.assertIn("$(git rev-parse HEAD)", steps[dispatch]["run"])

        publisher = Path(".github/workflows/sync_publish.yml").read_text(encoding="utf-8")
        self.assertEqual(publisher.count('-f "revision=${{ steps.commit.outputs.revision }}"'), 2)
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                self.assertIn("revision", workflow[True]["workflow_dispatch"]["inputs"])
                self.assertIn("force", workflow[True]["workflow_dispatch"]["inputs"])
                steps = workflow["jobs"]["deploy"]["steps"]
                checkout = steps[0]
                self.assertEqual(checkout["with"]["ref"], "${{ inputs.revision || github.sha }}")
                self.assertEqual(checkout["with"]["fetch-depth"], 0)
                self.assertIn("deployment_handoff preflight", steps[1]["run"])
                deploy_steps = [step for step in steps[2:] if step.get("name") == "Deploy public site" or "deploy-pages@" in step.get("uses", "")]
                self.assertTrue(deploy_steps)
                self.assertTrue(all("steps.handoff.outputs.deploy == 'true'" in step.get("if", "") for step in deploy_steps))

    def test_same_public_bytes_do_not_create_a_new_handoff(self):
        with fixture_repository() as (first, same_public, _):
            self.assertTrue(handoff.public_content_equal(first, same_public))
            self.assertFalse(handoff.public_content_equal("bad", same_public))
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", same_public])
            with patch.object(handoff, "live_revision", return_value=first), patch.object(
                handoff.subprocess, "run", wraps=subprocess.run
            ) as run:
                self.assertEqual(handoff.dispatch(same_public, "owner/repo"), 0)
                self.assertFalse(any(call.args[0][0] == "gh" for call in run.call_args_list))

    def test_live_receipt_must_match_target(self):
        response = io.BytesIO(b'{"target":"github-pages","revision":"' + b"a" * 40 + b'"}')
        with patch.object(handoff, "urlopen", return_value=response):
            self.assertIsNone(handoff.live_revision("https://example.invalid/deployment.json", "cloudflare-pages"))

    def test_interrupted_handoff_dispatches_both_targets(self):
        with fixture_repository() as (first, _, corrected):
            real_run = subprocess.run
            calls = []

            def run(command, **kwargs):
                if command[0] == "gh":
                    calls.append(command)
                    return subprocess.CompletedProcess(command, 0, "", "")
                return real_run(command, **kwargs)

            with patch.object(handoff, "live_revision", return_value=first), patch.object(
                handoff.subprocess, "run", side_effect=run
            ):
                self.assertEqual(handoff.dispatch(corrected, "owner/repo"), 0)
            self.assertEqual(len(calls), 2)
            self.assertEqual({call[3] for call in calls}, {"pages.yml", "cloudflare_pages.yml"})
            self.assertTrue(all(f"revision={corrected}" in call for call in calls))

    def test_partial_dispatch_failure_is_retryable_per_target(self):
        with fixture_repository() as (first, _, corrected):
            real_run = subprocess.run
            calls = []

            def run(command, **kwargs):
                if command[0] == "gh":
                    calls.append(command[3])
                    return subprocess.CompletedProcess(
                        command, 1 if command[3] == "pages.yml" else 0, "", "failure"
                    )
                return real_run(command, **kwargs)

            with patch.object(handoff, "live_revision", return_value=first), patch.object(
                handoff.subprocess, "run", side_effect=run
            ):
                self.assertEqual(handoff.dispatch(corrected, "owner/repo"), 1)
            self.assertEqual(set(calls), {"pages.yml", "cloudflare_pages.yml"})

            calls.clear()
            with patch.object(handoff, "live_revision", side_effect=[first, corrected]), patch.object(
                handoff.subprocess, "run", side_effect=run
            ):
                self.assertEqual(handoff.dispatch(corrected, "owner/repo"), 1)
            self.assertEqual(calls, ["pages.yml"])

    def test_preflight_skips_duplicate_and_obsolete_revisions(self):
        with fixture_repository() as (first, same_public, corrected):
            subprocess.check_call(["git", "checkout", "-q", same_public])
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", same_public])
            with patch.object(handoff, "live_revision", return_value=same_public), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(same_public, "github-pages"), 0)
                self.assertIn("deploy=false", Path("output").read_text())
            Path("output").unlink()
            with patch.object(handoff, "live_revision", return_value=same_public), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(same_public, "github-pages", force=True), 0)
                self.assertIn("deploy=true", Path("output").read_text())
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", corrected])
            with patch.object(handoff, "live_revision", return_value=first), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(same_public, "github-pages"), 0)
                self.assertIn("deploy=false", Path("output").read_text())
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", same_public])
            Path("output").unlink()
            with patch.object(handoff, "live_revision", return_value=first), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(same_public, "github-pages"), 0)
                self.assertIn("deploy=true", Path("output").read_text())
            with self.assertRaisesRegex(ValueError, "differs from requested"):
                handoff.preflight(corrected, "github-pages")

    def test_preflight_never_replaces_newer_live_revision_with_older_identity(self):
        with fixture_repository() as (_, _, corrected):
            Path("source.txt").write_text("new source, same public bytes", encoding="utf-8")
            subprocess.check_call(["git", "add", "source.txt"])
            subprocess.check_call(["git", "commit", "-qm", "newer source revision"])
            newer = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", newer])
            subprocess.check_call(["git", "checkout", "-q", corrected])
            with patch.object(handoff, "live_revision", return_value=newer), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(corrected, "github-pages", force=True), 0)
            self.assertIn("deploy=false", Path("output").read_text())


if __name__ == "__main__":
    unittest.main()
