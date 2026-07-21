import unittest
from pathlib import Path


class AndroidWrapperSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(
            "android-wrapper/src/com/torahpod/app/MainActivity.java"
        ).read_text(encoding="utf-8")

    def test_startup_exposes_release_identity_and_accessible_status(self):
        self.assertIn('versionLabel.setText("Version " + installedVersionLabel())', self.source)
        self.assertIn("getLongVersionCode()", self.source)
        self.assertIn("ACCESSIBILITY_LIVE_REGION_POLITE", self.source)
        self.assertIn("retryButton = new Button(this)", self.source)

    def test_connectivity_requires_an_internet_capable_network(self):
        self.assertIn("getNetworkCapabilities(network)", self.source)
        self.assertIn("NetworkCapabilities.NET_CAPABILITY_INTERNET", self.source)

    def test_renderer_failure_is_owned_and_recovered(self):
        self.assertIn("onRenderProcessGone", self.source)
        self.assertIn("view.getParent() instanceof ViewGroup", self.source)
        self.assertIn("((ViewGroup) view.getParent()).removeView(view)", self.source)
        self.assertIn("webView = null", self.source)
        self.assertIn("recreate()", self.source)

    def test_build_removes_stale_package_intermediates(self):
        build_script = Path("android-wrapper/build-apk.ps1").read_text(encoding="utf-8")
        self.assertIn("$Unsigned, $Aligned, $ProtoApk", build_script)
        self.assertIn("$ModuleZip, $ProtoZip, $Apk, $Aab", build_script)


if __name__ == "__main__":
    unittest.main()
