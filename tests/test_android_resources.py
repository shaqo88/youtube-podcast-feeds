from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class AndroidNotificationResourceTests(unittest.TestCase):
    def test_notification_controls_are_localized(self) -> None:
        root = Path("android-wrapper/res")
        names = {
            "playback_channel_name",
            "playback_channel_description",
            "play",
            "pause",
            "stop",
            "back_15_seconds",
            "forward_30_seconds",
        }
        for directory in ("values", "values-he"):
            with self.subTest(resources=directory):
                tree = ET.parse(root / directory / "strings.xml")
                values = {
                    node.attrib["name"]: (node.text or "").strip()
                    for node in tree.getroot().findall("string")
                }
                self.assertTrue(names.issubset(values))
                self.assertTrue(all(values[name] for name in names))

    def test_native_service_uses_localized_notification_resources(self) -> None:
        source = Path(
            "android-wrapper/src/com/torahpod/app/NativeAudioService.java"
        ).read_text(encoding="utf-8")
        for resource in (
            "pause",
            "play",
            "stop",
            "back_15_seconds",
            "forward_30_seconds",
            "playback_channel_name",
            "playback_channel_description",
        ):
            with self.subTest(resource=resource):
                self.assertIn(f"R.string.{resource}", source)

