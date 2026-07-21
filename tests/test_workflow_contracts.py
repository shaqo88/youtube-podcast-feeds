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


if __name__ == "__main__":
    unittest.main()
