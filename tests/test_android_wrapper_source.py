import unittest
import json
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

    def test_build_accepts_standard_ci_toolchain_locations(self):
        build_script = Path("android-wrapper/build-apk.ps1").read_text(encoding="utf-8")
        self.assertIn("$env:ANDROID_HOME", build_script)
        self.assertIn("$env:JAVA_HOME", build_script)
        self.assertIn("$env:ANDROID_BUILD_TOOLS_VERSION", build_script)
        self.assertIn('$TargetApi = 36', build_script)
        self.assertIn('"36.0.0"', build_script)
        self.assertIn("dump badging $Apk", build_script)
        self.assertIn("targetSdkVersion:'$TargetApi'", build_script)

    def test_release_candidate_identity_is_locked(self):
        version = json.loads(
            Path("android-wrapper/release-version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(version), {"versionName", "versionCode"})
        self.assertRegex(version["versionName"], r"^\d+\.\d+\.\d+$")
        self.assertIsInstance(version["versionCode"], int)
        self.assertGreater(version["versionCode"], 0)
        build_script = Path("android-wrapper/build-apk.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('Join-Path $Root "release-version.json"', build_script)
        self.assertIn("Release version must match", build_script)
        workflow = Path(".github/workflows/android.yml").read_text(encoding="utf-8")
        self.assertIn("set-release-version.ps1 -Check", workflow)
        self.assertIn("build-apk.ps1 -Configuration debug", workflow)
        self.assertIn('"platforms;android-36" "build-tools;36.0.0"', workflow)
        self.assertNotIn('-VersionCode 14 -VersionName "0.3.8"', workflow)
        self.assertIn(
            "actions/setup-java@03ad4de0992f5dab5e18fcb136590ce7c4a0ac95",
            workflow,
        )
        self.assertIn(
            "android-actions/setup-android@40fd30fb8d7440372e1316f5d1809ec01dcd3699",
            workflow,
        )
        readme = Path("android-wrapper/README.md").read_text(encoding="utf-8")
        self.assertIn("set-release-version.ps1 -Bump patch", readme)

    def test_release_workflow_is_approval_gated_and_does_not_publish(self):
        workflow = Path(".github/workflows/android_release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("environment: google-play-release", workflow)
        self.assertIn("ANDROID_RELEASE_KEYSTORE_BASE64", workflow)
        self.assertIn("bundletool checksum mismatch", workflow)
        self.assertIn("release-metadata.json", workflow)
        self.assertIn("Remove-Item -LiteralPath $keystore", workflow)
        self.assertNotIn("androidpublisher", workflow)
        self.assertNotIn("service-account", workflow)

    def test_release_bump_is_monotonic_and_source_controlled(self):
        script = Path("android-wrapper/set-release-version.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("$CurrentCode + 1", script)
        self.assertIn("VersionName must be greater", script)
        self.assertIn("VersionCode must be greater", script)
        self.assertIn("SupportsShouldProcess", script)

    def test_listener_data_and_webview_debug_surfaces_are_hardened(self):
        manifest = Path("android-wrapper/AndroidManifest.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn('android:allowBackup="false"', manifest)
        self.assertIn('android:fullBackupContent="false"', manifest)
        self.assertIn("WebView.setWebContentsDebuggingEnabled(false)", self.source)
        self.assertIn("settings.setSafeBrowsingEnabled(true)", self.source)
        self.assertIn("settings.setAllowFileAccess(false)", self.source)
        self.assertIn("settings.setAllowContentAccess(false)", self.source)

    def test_native_playback_obeys_audio_focus_and_noisy_route_changes(self):
        service = Path(
            "android-wrapper/src/com/torahpod/app/NativeAudioService.java"
        ).read_text(encoding="utf-8")
        self.assertIn("new AudioFocusRequest.Builder", service)
        self.assertIn("setWillPauseWhenDucked(true)", service)
        self.assertIn("requestAudioFocus()", service)
        self.assertIn("abandonAudioFocus()", service)
        self.assertIn("AudioManager.ACTION_AUDIO_BECOMING_NOISY", service)
        self.assertIn("registerNoisyReceiver()", service)
        self.assertIn("unregisterNoisyReceiver()", service)
        self.assertIn("pauseForAudioFocusLoss(true)", service)


if __name__ == "__main__":
    unittest.main()
