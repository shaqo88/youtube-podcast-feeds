import unittest
from pathlib import Path


class WorkflowContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
