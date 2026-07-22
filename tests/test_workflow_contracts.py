import unittest
from pathlib import Path

import yaml


class WorkflowContractTests(unittest.TestCase):
    def test_validation_runs_when_its_test_suite_changes(self):
        workflow_text = Path(".github/workflows/validate.yml").read_text(
            encoding="utf-8"
        )
        workflow = yaml.safe_load(workflow_text)
        push_paths = workflow[True]["push"]["paths"]
        self.assertIn("tests/**", push_paths)
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
        self.assertEqual(
            setup_node["uses"],
            "actions/setup-node@6044e13b5dc448c55e2357c09f80417699197238",
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


if __name__ == "__main__":
    unittest.main()
