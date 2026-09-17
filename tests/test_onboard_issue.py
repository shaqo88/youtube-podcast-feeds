from __future__ import annotations

import unittest

from podcast_feeds.onboard_issue import (
    OnboardingNotReady,
    _config_for_issue,
    _first_metadata_value,
)


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


class OnboardingMetadataTests(unittest.TestCase):
    def test_discovered_metadata_is_trimmed_before_config_generation(self) -> None:
        self.assertEqual(
            _first_metadata_value([{"title": "  הרב גיל  "}], "title"),
            "הרב גיל",
        )

    def test_whitespace_only_metadata_does_not_hide_a_later_value(self) -> None:
        self.assertEqual(
            _first_metadata_value(
                [{"author": "  "}, {"author": " הרב גיל אוריאן "}],
                "author",
            ),
            "הרב גיל אוריאן",
        )


if __name__ == "__main__":
    unittest.main()
