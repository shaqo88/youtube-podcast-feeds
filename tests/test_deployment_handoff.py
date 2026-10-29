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
    def test_successor_requires_newer_main_history_and_private_release_index(self):
        release_id, payload_digest = "e" * 64, "f" * 64
        with fixture_repository() as (first, _, corrected):
            real_git = handoff.git

            def git(*args, **kwargs):
                if args[:1] == ("fetch",):
                    return subprocess.CompletedProcess(args, 0, "", "")
                return real_git(*args, **kwargs)

            with patch.object(handoff, "git", side_effect=git):
                receipt = (corrected, release_id, payload_digest)
                self.assertTrue(handoff.retained_successor(first, receipt, release_lookup=lambda _: receipt))
                self.assertFalse(handoff.retained_successor(first, receipt, release_lookup=lambda _: (corrected, "d" * 64, payload_digest)))
                self.assertFalse(handoff.retained_successor(first, receipt, release_lookup=lambda _: (corrected, release_id, "d" * 64)))
                def missing(_revision):
                    raise FileNotFoundError("release index is not available")
                self.assertFalse(handoff.retained_successor(first, receipt, release_lookup=missing))
                self.assertFalse(handoff.retained_successor(corrected, (first, release_id, payload_digest), release_lookup=lambda _: receipt))
                self.assertFalse(handoff.retained_successor(first, ("a" * 40, release_id, payload_digest), release_lookup=lambda _: receipt))
                # Even a real descendant must have reached origin/main.
                subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", first])
                self.assertFalse(handoff.retained_successor(first, receipt, release_lookup=lambda _: receipt))

    def test_publisher_can_verify_successor_but_deployment_stays_exact(self):
        revision, successor = "a" * 40, "b" * 40
        expected_id, expected_digest = "c" * 64, "d" * 64
        receipt = (successor, "e" * 64, "f" * 64)
        with patch.object(handoff, "live_artifact", return_value=receipt), patch.object(
            handoff, "retained_successor", return_value=True
        ) as retained:
            args = dict(attempts=1, release_id=expected_id, payload_digest=expected_digest)
            self.assertEqual(handoff.verify(revision, "github-pages", **args), 1)
            retained.assert_not_called()
            self.assertEqual(handoff.verify(revision, "github-pages", allow_superseded=True, **args), 0)
            retained.assert_called_once_with(revision, receipt)
        with patch.object(handoff, "live_artifact", return_value=(revision, "e" * 64, "f" * 64)), patch.object(
            handoff, "retained_successor"
        ) as retained:
            self.assertEqual(handoff.verify(revision, "github-pages", allow_superseded=True, **args), 1)
            retained.assert_not_called()
        with self.assertRaises(ValueError):
            handoff.verify(revision, "github-pages", attempts=1, allow_superseded=True)

    def test_validated_main_releases_publish_without_waiting_for_sync_writer(self):
        workflow = yaml.safe_load(Path(".github/workflows/publish_committed_release.yml").read_text(encoding="utf-8"))
        trigger = workflow.get("on", workflow.get(True))["workflow_run"]
        self.assertEqual(trigger["workflows"], ["Validate Podcast Feeds"])
        self.assertEqual(trigger["branches"], ["main"])
        guard = workflow["jobs"]["publish"]["if"]
        for condition in ("conclusion == 'success'", "event == 'push'", "head_repository.full_name == github.repository"):
            self.assertIn(condition, guard)
        self.assertNotEqual(workflow["concurrency"]["group"], "repo-writer-main")
        self.assertEqual(workflow["concurrency"]["queue"], "max")
        sync = yaml.safe_load(Path(".github/workflows/sync.yml").read_text(encoding="utf-8"))
        verify = [step for step in sync["jobs"]["sync"]["steps"] if step.get("name", "").startswith("Verify retained release on")]
        self.assertEqual(len(verify), 2)
        for step in verify:
            self.assertIn("--allow-superseded", step["run"])
            self.assertIn("--attempts 120", step["run"])
            self.assertIn("R2_RELEASE_READ_ACCESS_KEY", step["env"]["R2_RELEASE_ACCESS_KEY"])

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

    def test_mirror_verification_waits_for_dispatched_deployment(self):
        revision = "a" * 40
        observed = iter([None] * 20 + [revision])
        with patch.object(handoff, "live_revision", side_effect=lambda *_: next(observed)), patch.object(
            handoff.time, "sleep"
        ) as sleep:
            self.assertEqual(handoff.verify(revision, "github-pages", attempts=120), 0)
        self.assertEqual(sleep.call_count, 20)

    def test_main_is_rechecked_after_preparation_before_target_mutation(self):
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                steps = workflow["jobs"]["deploy"]["steps"]
                first = next(i for i, step in enumerate(steps) if step.get("id") == "handoff")
                prepared = next(i for i, step in enumerate(steps) if step.get("name") == "Add target-specific deployment receipt")
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

    def test_newer_main_after_final_preflight_gets_its_own_handoff(self):
        for name in ("pages.yml", "cloudflare_pages.yml"):
            with self.subTest(deployment=name):
                workflow = yaml.safe_load(Path(".github/workflows", name).read_text(encoding="utf-8"))
                steps = workflow["jobs"]["deploy"]["steps"]
                verified = next(i for i, step in enumerate(steps) if step.get("name") == "Verify exact live revision")
                reconcile = next(i for i, step in enumerate(steps) if step.get("name") == "Hand newer main content to deployment")
                self.assertLess(verified, reconcile)
                self.assertIn("deployment_handoff reconcile", steps[reconcile]["run"])

        with fixture_repository() as (first, same_public, corrected):
            subprocess.check_call(["git", "checkout", "-q", first])
            real_run = subprocess.run
            calls = []

            def run(command, **kwargs):
                if command[0] == "gh":
                    calls.append(command)
                    return subprocess.CompletedProcess(command, 0, "", "")
                return real_run(command, **kwargs)

            with patch.object(handoff.subprocess, "run", side_effect=run), patch.object(
                handoff, "live_revision", return_value=first
            ), patch.object(handoff, "live_artifact", return_value=None):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo"), 0)
            self.assertEqual(len(calls), 1)
            self.assertIn("pages.yml", calls[0])
            self.assertIn(f"revision={corrected}", calls[0])

            calls.clear()
            with patch.object(handoff.subprocess, "run", side_effect=run), patch.object(
                handoff, "live_revision", return_value=corrected
            ):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo"), 0)
            self.assertEqual(calls, [])

            def fail(command, **kwargs):
                if command[0] == "gh":
                    return subprocess.CompletedProcess(command, 1, "", "rate limited")
                return real_run(command, **kwargs)

            with patch.object(handoff.subprocess, "run", side_effect=fail), patch.object(
                handoff, "live_revision", return_value=first
            ):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo"), 1)

            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", same_public])
            calls.clear()
            with patch.object(handoff.subprocess, "run", side_effect=run):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo"), 0)
            self.assertEqual(calls, [])

    def test_artifact_reconcile_requires_retained_newer_main_and_dispatches_its_id(self):
        release_id = "e" * 64
        with fixture_repository() as (first, _, corrected):
            subprocess.check_call(["git", "checkout", "-q", first])
            real_run = subprocess.run
            calls = []

            def run(command, **kwargs):
                if command[0] == "gh":
                    calls.append(command)
                    return subprocess.CompletedProcess(command, 0, "", "")
                return real_run(command, **kwargs)

            def unavailable(_revision):
                raise FileNotFoundError("newer release has not been retained")

            with patch.object(handoff.subprocess, "run", side_effect=run), patch.object(
                handoff, "live_revision", return_value=first
            ), patch.object(handoff, "live_artifact", return_value=None):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo",
                                                   artifact_mode=True, release_lookup=unavailable), 1)
                self.assertEqual(calls, [])
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo",
                                                   artifact_mode=True, release_lookup=lambda revision: release_id), 0)
            self.assertEqual(len(calls), 1)
            self.assertIn(f"revision={corrected}", calls[0])
            self.assertIn(f"release_id={release_id}", calls[0])

            # A newer Git tree deployed by the legacy path still needs its
            # retained artifact identity before this target is complete.
            calls.clear()
            with patch.object(handoff.subprocess, "run", side_effect=run), patch.object(
                handoff, "live_revision", return_value=corrected
            ), patch.object(handoff, "live_artifact", return_value=None):
                self.assertEqual(handoff.reconcile(first, "github-pages", "owner/repo",
                                                   artifact_mode=True, release_lookup=lambda revision: release_id), 0)
            self.assertEqual(len(calls), 1)
            self.assertIn(f"release_id={release_id}", calls[0])

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

    def test_live_receipt_uses_project_user_agent(self):
        response = io.BytesIO(b'{"target":"cloudflare-pages","revision":"' + b"a" * 40 + b'"}')
        with patch.object(handoff, "urlopen", return_value=response) as open_url:
            self.assertEqual(handoff.live_revision("https://example.invalid/deployment.json", "cloudflare-pages"), "a" * 40)
        self.assertEqual(open_url.call_args.args[0].get_header("User-agent"), "torah-pod-publication/1.0")

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

    def test_artifact_mode_skips_automatic_legacy_deploy_but_allows_forced_recovery(self):
        with fixture_repository() as (_, current, _):
            subprocess.check_call(["git", "checkout", "-q", current])
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", current])
            output = Path.cwd() / "output"
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), patch.object(
                handoff, "live_revision", return_value=None
            ):
                self.assertEqual(handoff.preflight(current, "github-pages", artifact_mode=True), 0)
                self.assertIn("deploy=false", output.read_text())
                output.unlink()
                self.assertEqual(handoff.preflight(current, "github-pages", force=True, artifact_mode=True), 0)
                self.assertIn("deploy=true", output.read_text())

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

    def test_retained_release_duplicate_and_mismatched_identity(self):
        release_id = "a" * 64
        other_id = "b" * 64
        with fixture_repository() as (_, same_public, _):
            subprocess.check_call(["git", "checkout", "-q", same_public])
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", same_public])
            with patch.object(handoff, "live_revision", return_value=same_public), patch.object(
                handoff, "live_artifact", return_value=(same_public, release_id, "c" * 64)
            ), patch.dict(os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}):
                self.assertEqual(handoff.preflight(same_public, "github-pages", release_id=release_id), 0)
                self.assertIn("deploy=false", Path("output").read_text())
                with self.assertRaisesRegex(ValueError, "different retained release"):
                    handoff.preflight(same_public, "github-pages", release_id=other_id, force=True)

    def test_deliberate_retained_rollback_when_main_and_target_advanced(self):
        release_id = "a" * 64
        with fixture_repository() as (first, _, corrected):
            subprocess.check_call(["git", "checkout", "-q", first])
            output = Path.cwd() / "output"
            with patch.object(handoff, "live_revision", return_value=corrected), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(output)}
            ):
                self.assertEqual(handoff.preflight(first, "github-pages", release_id=release_id,
                                                   artifact_mode=True), 0)
                self.assertIn("deploy=false", output.read_text())
                output.unlink()
                self.assertEqual(handoff.preflight(first, "github-pages", release_id=release_id,
                                                   artifact_mode=True, rollback=True), 0)
                self.assertIn("deploy=true", output.read_text())
                with self.assertRaisesRegex(ValueError, "rollback requires"):
                    handoff.preflight(first, "github-pages", artifact_mode=True, rollback=True)

    def test_retained_release_verification_needs_exact_payload_digest(self):
        revision, release_id, payload_digest = "a" * 40, "b" * 64, "c" * 64
        with patch.object(handoff, "live_artifact", side_effect=[
            (revision, release_id, "d" * 64), (revision, release_id, payload_digest)
        ]), patch.object(handoff.time, "sleep"):
            self.assertEqual(handoff.verify(revision, "github-pages", attempts=2, delay_seconds=0,
                                            release_id=release_id, payload_digest=payload_digest), 0)

    def test_preflight_allows_rollback_content_when_newer_live_bytes_differ(self):
        with fixture_repository() as (first, _, corrected):
            Path("public/feed.xml").write_text("first", encoding="utf-8")
            subprocess.check_call(["git", "add", "public/feed.xml"])
            subprocess.check_call(["git", "commit", "-qm", "revert public feed"])
            reverted = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            subprocess.check_call(["git", "update-ref", "refs/remotes/origin/main", reverted])
            subprocess.check_call(["git", "checkout", "-q", first])
            with patch.object(handoff, "live_revision", return_value=corrected), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(Path.cwd() / "output")}
            ):
                self.assertEqual(handoff.preflight(first, "github-pages"), 0)
            self.assertIn("deploy=true", Path("output").read_text())


if __name__ == "__main__":
    unittest.main()
