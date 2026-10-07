[CmdletBinding()]
param(
    [ValidateSet("debug", "release")][string]$Configuration = "debug",
    [ValidateSet("production", "preview")][string]$Environment = "production",
    [switch]$Bundle,
    [string]$VersionName,
    [int]$VersionCode
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Version = Get-Content -Raw (Join-Path $Root "release-version.json") | ConvertFrom-Json
if (($VersionName -and $VersionName -ne $Version.versionName) -or ($VersionCode -and $VersionCode -ne $Version.versionCode)) {
    throw "Release version must match release-version.json"
}
$VersionName = [string]$Version.versionName
$VersionCode = [int]$Version.versionCode
$TargetApi = 36
$MinApi = 24
$ToolsVersion = if ($env:ANDROID_BUILD_TOOLS_VERSION) { $env:ANDROID_BUILD_TOOLS_VERSION } else { "36.0.0" }
$SdkRoot = $env:ANDROID_HOME
if (!$SdkRoot) { throw "ANDROID_HOME is required." }
if (!$env:JAVA_HOME -or !(Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe"))) { throw "Set JAVA_HOME to a JDK supported by the pinned Gradle wrapper (JDK 21 recommended)." }
$BuildTools = Join-Path $SdkRoot "build-tools\$ToolsVersion"
$Package = if ($Environment -eq "preview") { "com.torahpod.app.preview" } else { "com.torahpod.app" }
if ($Configuration -eq "release") {
    foreach ($name in @("TORAH_POD_RELEASE_KEYSTORE", "TORAH_POD_RELEASE_KEYSTORE_PASSWORD", "TORAH_POD_RELEASE_KEY_ALIAS", "TORAH_POD_RELEASE_KEY_PASSWORD")) {
        if (![Environment]::GetEnvironmentVariable($name)) { throw "Missing release signing configuration: $name" }
    }
}
$Icon = Join-Path $Root "res\drawable\icon.png"
New-Item -ItemType Directory -Force (Split-Path $Icon -Parent) | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "..\public\assets\icon-192.png") -Destination $Icon -Force
$WrapperJar = Join-Path $Root "gradle\wrapper\gradle-wrapper.jar"
if ((Get-FileHash -LiteralPath $WrapperJar -Algorithm SHA256).Hash -ne "7D3A4AC4DE1C32B59BC6A4EB8ECB8E612CCD0CF1AE1E99F66902DA64DF296172") { throw "Gradle wrapper checksum mismatch" }
$Flavor = (Get-Culture).TextInfo.ToTitleCase($Environment)
$Type = (Get-Culture).TextInfo.ToTitleCase($Configuration)
$Tasks = @("clean", "assemble$Flavor$Type")
if ($Bundle) { $Tasks += "bundle$Flavor$Type" }
& (Join-Path $Root "gradlew.bat") --project-dir $Root --no-daemon @Tasks
if ($LASTEXITCODE -ne 0) { throw "Gradle build failed." }
$SourceApk = Join-Path $Root "build\outputs\apk\$Environment\$Configuration\TorahPod-$Environment-$Configuration.apk"
$Apk = Join-Path $Root "build\torah-pod-$Configuration.apk"
Copy-Item -LiteralPath $SourceApk -Destination $Apk -Force
& (Join-Path $BuildTools "apksigner.bat") verify --verbose $Apk
if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed." }
$Badging = & (Join-Path $BuildTools "aapt.exe") dump badging $Apk
if ($LASTEXITCODE -ne 0) { throw "APK inspection failed." }
$BadgingText = $Badging -join "`n"
if (!$BadgingText.Contains("package: name='$Package' versionCode='$VersionCode' versionName='$VersionName'")) { throw "Built APK package/version mismatch." }
if ($BadgingText -notmatch "targetSdkVersion:'$TargetApi'" -or $BadgingText -notmatch "sdkVersion:'$MinApi'") { throw "Built APK SDK mismatch." }
if ($Bundle) {
    $Aab = Join-Path $Root "build\torah-pod-$Configuration.aab"
    Copy-Item -LiteralPath (Join-Path $Root "build\outputs\bundle\$Environment$Type\TorahPod-$Environment-$Configuration.aab") -Destination $Aab -Force
    & (Join-Path $env:JAVA_HOME "bin\jarsigner.exe") -verify $Aab
    if ($LASTEXITCODE -ne 0) { throw "AAB signature verification failed." }
    if ($env:BUNDLETOOL_JAR) {
        & (Join-Path $env:JAVA_HOME "bin\java.exe") -jar $env:BUNDLETOOL_JAR validate "--bundle=$Aab"
        if ($LASTEXITCODE -ne 0) { throw "Bundle validation failed." }
    }
}
Write-Host "Verified $Package $VersionName ($VersionCode), minimum API ${MinApi}: $Apk"
