from __future__ import annotations

import unittest

from podcast_feeds.onboard_issue import OnboardingNotReady, _config_for_issue


class OnboardingRightsTests(unittest.TestCase):
    def test_private_intake_requires_requester_authority_confirmation(self) -> None:
        issue = {
            "number": 42,
            "body": "- Source type: YouTube\n- YouTube URL: https://www.youtube.com/@example",
            "labels": [
                {"name": "needs-approval"},
                {"name": "approved"},
                {"name": "youtube-onboarding"},
            ],
        }

        with self.assertRaisesRegex(OnboardingNotReady, "did not confirm authority"):
            _config_for_issue(
                issue,
                "shaqo88/torah-pod-intake",
                require_rights_confirmation=True,
                include_issue_url=False,
            )


if __name__ == "__main__":
    unittest.main()
