import re
import unittest
from pathlib import Path

import yaml


class WorkflowContractTests(unittest.TestCase):
    def test_external_actions_are_pinned_to_full_commit_shas(self):
        for path in Path(".github/workflows").glob("*.yml"):
            workflow_text = path.read_text(encoding="utf-8")
            references = re.findall(
                r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", workflow_text, re.MULTILINE
            )
            for reference in references:
                if reference.startswith("./"):
                    continue
                with self.subTest(workflow=path.name, reference=reference):
                    self.assertIn("@", reference)
                    revision = reference.rsplit("@", 1)[1]
                    self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_validation_runs_when_its_test_suite_changes(self):
        workflow_text = Path(".github/workflows/validate.yml").read_text(
            encoding="utf-8"
        )
        workflow = yaml.safe_load(workflow_text)
        push_paths = workflow[True]["push"]["paths"]
        pull_request_paths = workflow[True]["pull_request"]["paths"]
        self.assertIn("tests/**", push_paths)
        self.assertIn("tests/**", pull_request_paths)
        self.assertIn("requirements.txt", pull_request_paths)
        self.assertIn(".github/dependabot.yml", pull_request_paths)
        self.assertIn("python -m unittest discover -s tests", workflow_text)

    def test_every_workflow_has_permissions_and_bounded_jobs(self):
        for path in Path(".github/workflows").glob("*.yml"):
            with self.subTest(workflow=path.name):
                workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIsInstance(workflow.get("permissions"), dict)
                jobs = workflow.get("jobs") or {}
                self.assertTrue(jobs)
                for name, job in jobs.items():
                    with self.subTest(workflow=path.name, job=name):
                        # Reusable workflow call jobs inherit the bounded runtime
                        # from the called workflow; GitHub does not permit
                        # timeout-minutes on a job that uses another workflow.
                        if job.get("uses"):
                            continue
                        self.assertIsInstance(job.get("timeout-minutes"), int)
                        self.assertGreater(job["timeout-minutes"], 0)
                        self.assertLessEqual(job["timeout-minutes"], 60)

    def test_credential_health_verifies_github_token_without_mutation(self):
        workflow = Path(".github/workflows/credential_health.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ONBOARDING_INTAKE_TOKEN", workflow)
        self.assertIn("https://api.github.com/repos/$INTAKE_REPOSITORY", workflow)
        self.assertIn("github-authentication-token-expiration", workflow)
        self.assertIn("--request GET", workflow)
        self.assertNotIn("/issues", workflow)
        self.assertNotIn("--request POST", workflow)
        self.assertNotIn("--request PATCH", workflow)

    def test_weekly_health_calculates_availability_objective(self):
        workflow = Path(".github/workflows/free_tier_health.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("--workflow production_availability.yml", workflow)
        self.assertIn("--event schedule", workflow)
        self.assertIn("--limit 3000", workflow)
        self.assertIn("podcast_feeds.workflow_slo", workflow)
        self.assertIn("availability-slo.json", workflow)
        self.assertIn("podcast_feeds.workflow_health", workflow)
        self.assertIn("workflow-health.json", workflow)
        self.assertIn("WORKFLOW_HEALTH_OUTCOME", workflow)

    def test_production_monitor_enforces_site_shell_and_response_policy(self):
        workflow = Path(
            ".github/workflows/production_availability.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Cloudflare Pages service worker", workflow)
        self.assertIn("Cloudflare Pages analytics beacon", workflow)
        self.assertIn("static.cloudflareinsights.com/beacon.min.js", workflow)
        self.assertIn("Cloudflare Pages analytics disclosure", workflow)
        self.assertIn("Cloudflare Web Analytics", workflow)
        self.assertIn("Cloudflare Pages anti-abuse disclosure", workflow)
        self.assertIn("Cloudflare Pages advertising disclosure", workflow)
        self.assertIn("Cloudflare Pages app JavaScript", workflow)
        self.assertIn("function setupAppNavigation()", workflow)
        self.assertIn("Cloudflare Pages stylesheet", workflow)
        self.assertIn(".app-bottom-nav", workflow)
        self.assertIn("Cloudflare Pages web manifest", workflow)
        self.assertIn("application/manifest+json", workflow)
        self.assertIn('require_contains "Content-Type"', workflow)
        self.assertIn("check_headers", workflow)
        for requirement in (
            "max-age=0",
            "must-revalidate",
            "script-src-attr 'none'",
            "style-src 'self'; style-src-attr 'none'",
            "unsafe-inline",
            "Strict-Transport-Security",
            "X-Frame-Options",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
            "Origin-Agent-Cluster",
        ):
            self.assertIn(requirement, workflow)

    def test_deployments_publish_and_monitor_revision_provenance(self):
        workflow_dir = Path(".github/workflows")
        for workflow_name in (
            "cloudflare_pages.yml",
            "pages.yml",
            "sync.yml",
            "approve_onboarding.yml",
        ):
            workflow = (workflow_dir / workflow_name).read_text(encoding="utf-8")
            with self.subTest(workflow=workflow_name):
                self.assertIn("podcast_feeds.deployment_manifest", workflow)
                self.assertIn("public-dist/deployment.json", workflow)

        worker_deploy = (workflow_dir / "deploy_onboarding_worker.yml").read_text(
            encoding="utf-8"
        )
        for marker in ("BUILD_SHA", "BUILD_TIME", "BUILD_RUN_ID", "BUILD_RUN_URL"):
            self.assertIn(marker, worker_deploy)

        production = (workflow_dir / "production_availability.yml").read_text(
            encoding="utf-8"
        )
        weekly = (workflow_dir / "free_tier_health.yml").read_text(encoding="utf-8")
        for workflow in (production, weekly):
            self.assertIn("fetch-depth: 0", workflow)
            self.assertIn("podcast_feeds.deployment_health", workflow)
            self.assertIn("cloudflare-pages.json", workflow)
            self.assertIn("github-pages.json", workflow)
            self.assertIn("onboarding-worker.json", workflow)

    def test_wrangler_deployments_use_one_exact_version(self):
        workflow_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path(".github/workflows").glob("*.yml")
        )
        invocations = [
            token for token in workflow_text.split() if token.startswith("wrangler@")
        ]
        self.assertTrue(invocations)
        self.assertEqual(set(invocations), {"wrangler@4.113.0"})

    def test_sync_node_runtime_supports_pinned_wrangler(self):
        workflow = yaml.safe_load(
            Path(".github/workflows/sync.yml").read_text(encoding="utf-8")
        )
        setup_node = next(
            step
            for step in workflow["jobs"]["sync"]["steps"]
            if str(step.get("uses", "")).startswith("actions/setup-node@")
        )
        self.assertEqual(setup_node["with"]["node-version"], "22")
        self.assertRegex(
            setup_node["uses"],
            r"^actions/setup-node@[0-9a-f]{40}$",
        )

    def test_sync_forced_403_retry_is_manual_only(self):
        workflow = yaml.safe_load(
            Path(".github/workflows/sync.yml").read_text(encoding="utf-8")
        )
        retry_input = workflow[True]["workflow_dispatch"]["inputs"]["force_retry_403"]
        self.assertEqual(retry_input["type"], "boolean")
        self.assertFalse(retry_input["default"])

        sync_step = next(
            step
            for step in workflow["jobs"]["sync"]["steps"]
            if step.get("name") == "Sync episodes"
        )
        self.assertEqual(
            sync_step["env"]["FORCE_RETRY_403"],
            "${{ github.event_name == 'workflow_dispatch' && inputs.force_retry_403 || 'false' }}",
        )

    def test_sync_pot_provider_startup_cannot_block_cookie_fallback(self):
        workflow = Path(".github/workflows/sync.yml").read_text(encoding="utf-8")

        self.assertIn("timeout 30s docker rm -f bgutil-provider", workflow)
        self.assertIn("timeout 90s docker run --name bgutil-provider", workflow)
        self.assertIn("timeout 15s docker ps --filter name=bgutil-provider", workflow)
        self.assertIn("timeout 15s docker logs bgutil-provider", workflow)
        self.assertIn("YouTube sync may fall back to cookies.", workflow)

    def test_sync_falls_back_when_google_runner_is_offline(self):
        workflow = yaml.safe_load(
            Path(".github/workflows/sync.yml").read_text(encoding="utf-8")
        )
        preflight = workflow["jobs"]["preflight"]
        self.assertEqual(
            preflight["outputs"]["runner_labels"],
            "${{ steps.runner.outputs.labels }}",
        )
        runner_step = next(
            step
            for step in preflight["steps"]
            if step.get("name") == "Select an available YouTube runner"
        )
        script = runner_step["run"]
        self.assertIn("/actions/runners?per_page=100", script)
        self.assertIn('"google-youtube"', script)
        self.assertIn('labels=["ubuntu-latest"]', script)
        self.assertIn("Google YouTube runner is offline; using GitHub-hosted fallback.", script)
        self.assertEqual(
            workflow["jobs"]["sync"]["runs-on"],
            "${{ fromJSON(needs.preflight.outputs.runner_labels) }}",
        )

    def test_expected_notification_delivery_is_not_silently_ignored(self):
        workflow_names = (
            "credential_health.yml",
            "free_tier_health.yml",
            "notify_new_episodes.yml",
            "notify_added_podcast.yml",
            "notify_onboarding_request.yml",
        )
        for workflow_name in workflow_names:
            workflow = yaml.safe_load(
                Path(".github/workflows", workflow_name).read_text(encoding="utf-8")
            )
            send_steps = [
                step
                for job in workflow["jobs"].values()
                for step in job.get("steps", [])
                if "action-send-mail" in str(step.get("uses", ""))
                and "failure" not in step.get("name", "").lower()
            ]
            self.assertTrue(send_steps, workflow_name)
            for step in send_steps:
                with self.subTest(workflow=workflow_name, step=step.get("name")):
                    self.assertNotIn("continue-on-error", step)

        weekly = Path(".github/workflows/free_tier_health.yml").read_text(
            encoding="utf-8"
        )
        credential = Path(".github/workflows/credential_health.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAIL_ENABLED", weekly)
        self.assertIn("SMTP delivery canary", credential)

    def test_availability_mail_remains_decoupled_from_endpoint_health(self):
        workflow = yaml.safe_load(
            Path(".github/workflows/production_availability.yml").read_text(
                encoding="utf-8"
            )
        )
        mail_step = next(
            step
            for step in workflow["jobs"]["monitor"]["steps"]
            if step.get("name") == "Email availability state transition"
        )
        self.assertTrue(mail_step.get("continue-on-error"))

    def test_reliable_sync_uses_independent_workers_and_one_publisher(self):
        workflows = Path(".github/workflows")
        youtube = (workflows / "sync_youtube.yml").read_text(encoding="utf-8")
        reusable = (workflows / "source_worker.yml").read_text(encoding="utf-8")
        publisher = (workflows / "sync_publish.yml").read_text(encoding="utf-8")
        self.assertIn('response=""', youtube)
        self.assertIn("fallback_probe=true", youtube)
        self.assertIn("RUNNER_STATUS_TOKEN", youtube)
        self.assertIn("sync-worker-${{ inputs.lane }}", reusable)
        self.assertIn("podcast_feeds.sync_state capture", reusable)
        self.assertIn("workflows: [Sync YouTube Worker, Sync Drive Worker, Sync Existing Feed Worker]", publisher)
        self.assertIn("group: repo-writer-main", publisher)
        self.assertIn("gh workflow run pages.yml", publisher)
        self.assertIn("gh workflow run cloudflare_pages.yml", publisher)

    def test_malformed_cookies_do_not_stop_source_processing(self):
        legacy = Path(".github/workflows/sync.yml").read_text(encoding="utf-8")
        worker = Path(".github/workflows/source_worker.yml").read_text(encoding="utf-8")
        self.assertIn("continuing without cookie fallback", legacy)
        self.assertIn("continuing without it", worker)


if __name__ == "__main__":
    unittest.main()
