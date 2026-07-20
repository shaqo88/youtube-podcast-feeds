param(
    [ValidateSet("debug", "release")]
    [string]$Configuration = "debug"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Adb = Join-Path $env:USERPROFILE "scoop\apps\android-clt\current\platform-tools\adb.exe"
$Apk = Join-Path $Root "build\torah-pod-$Configuration.apk"

if (!(Test-Path $Apk)) {
    throw "APK not found at $Apk. Run .\build-apk.ps1 -Configuration $Configuration first."
}

& $Adb devices
& $Adb install -r $Apk
