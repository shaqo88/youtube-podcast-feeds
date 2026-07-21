import unittest
from pathlib import Path

import yaml


class WorkflowContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
