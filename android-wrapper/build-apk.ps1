param(
    [ValidateSet("debug", "release")]
    [string]$Configuration = "debug",
    [Nullable[int]]$VersionCode,
    [string]$VersionName,
    [switch]$Bundle
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Root
$ReleaseVersionFile = Join-Path $Root "release-version.json"
$ReleaseVersion = Get-Content -Raw -LiteralPath $ReleaseVersionFile | ConvertFrom-Json
$VersionCodeWasProvided = $PSBoundParameters.ContainsKey("VersionCode")
$VersionNameWasProvided = $PSBoundParameters.ContainsKey("VersionName")

if (!$VersionCodeWasProvided) {
    $VersionCode = [int]$ReleaseVersion.versionCode
}
if (!$VersionNameWasProvided) {
    $VersionName = [string]$ReleaseVersion.versionName
}
$Scoop = Join-Path $env:USERPROFILE "scoop\apps"
$BuildToolsVersion = if ($env:ANDROID_BUILD_TOOLS_VERSION) { $env:ANDROID_BUILD_TOOLS_VERSION } else { "35.0.0" }
$AndroidHome = @(
    $env:ANDROID_HOME,
    (Join-Path $Scoop "android-clt\current")
) | Where-Object {
    $_ -and (Test-Path -LiteralPath (Join-Path $_ "platforms\android-35\android.jar"))
} | Select-Object -First 1
$JavaHome = @(
    $env:JAVA_HOME,
    (Join-Path $Scoop "openjdk\26-35")
) | Where-Object {
    $_ -and (Test-Path -LiteralPath (Join-Path $_ "bin\javac.exe")) -and
        (Test-Path -LiteralPath (Join-Path $_ "bin\java.exe"))
} | Select-Object -First 1

if (!$AndroidHome) {
    throw "Android platform android-35 is missing. Set ANDROID_HOME to a complete SDK."
}

if (!$JavaHome) {
    throw "A complete JDK is missing. Set JAVA_HOME to a directory containing java.exe and javac.exe."
}

$BuildTools = Join-Path $AndroidHome "build-tools\$BuildToolsVersion"
$PlatformJar = Join-Path $AndroidHome "platforms\android-35\android.jar"
$Out = Join-Path $Root "build"
$Gen = Join-Path $Out "gen"
$Classes = Join-Path $Out "classes"
$Dex = Join-Path $Out "dex"
$Compiled = Join-Path $Out "compiled"
$Unsigned = Join-Path $Out "torah-pod-unsigned.apk"
$Aligned = Join-Path $Out "torah-pod-aligned.apk"
$Apk = Join-Path $Out "torah-pod-$Configuration.apk"
$ProtoApk = Join-Path $Out "torah-pod-proto.apk"
$ModuleRoot = Join-Path $Out "bundle-module"
$ModuleZip = Join-Path $Out "base.zip"
$Aab = Join-Path $Out "torah-pod-$Configuration.aab"
$ProtoZip = Join-Path $Out "torah-pod-proto.zip"
$Package = "com.torahpod.app"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $null
    )

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath failed with exit code $LASTEXITCODE"
        }
    } finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

if (!(Test-Path -LiteralPath (Join-Path $BuildTools "aapt2.exe"))) {
    throw "Android build-tools $BuildToolsVersion are missing at $BuildTools"
}

if ($VersionCode -lt 1) {
    throw "VersionCode must be a positive integer."
}

if ([string]::IsNullOrWhiteSpace($VersionName)) {
    throw "VersionName cannot be empty."
}

if ($Configuration -eq "release" -and
    ($VersionCode -ne [int]$ReleaseVersion.versionCode -or
     $VersionName -ne [string]$ReleaseVersion.versionName)) {
    throw "Release version must match ${ReleaseVersionFile}: $($ReleaseVersion.versionName) ($($ReleaseVersion.versionCode))."
}

if ($Configuration -eq "release") {
    $KeyStore = $env:TORAH_POD_RELEASE_KEYSTORE
    $KeyStorePassword = $env:TORAH_POD_RELEASE_KEYSTORE_PASSWORD
    $KeyAlias = $env:TORAH_POD_RELEASE_KEY_ALIAS
    $KeyPassword = $env:TORAH_POD_RELEASE_KEY_PASSWORD

    if ([string]::IsNullOrWhiteSpace($KeyStore) -or
        [string]::IsNullOrWhiteSpace($KeyStorePassword) -or
        [string]::IsNullOrWhiteSpace($KeyAlias) -or
        [string]::IsNullOrWhiteSpace($KeyPassword)) {
        throw "Release signing is not configured. Set TORAH_POD_RELEASE_KEYSTORE, TORAH_POD_RELEASE_KEYSTORE_PASSWORD, TORAH_POD_RELEASE_KEY_ALIAS, and TORAH_POD_RELEASE_KEY_PASSWORD."
    }

    if (!(Test-Path -LiteralPath $KeyStore -PathType Leaf)) {
        throw "Release keystore was not found: $KeyStore"
    }
} else {
    $KeyStore = Join-Path $Out "debug.keystore"
    $KeyStorePassword = "android"
    $KeyAlias = "androiddebugkey"
    $KeyPassword = "android"
}

if ($Bundle) {
    $BundleTool = if ($env:BUNDLETOOL_JAR) { $env:BUNDLETOOL_JAR } else { "C:\tmp\bundletool-all-1.18.3.jar" }
    if (!(Test-Path -LiteralPath $BundleTool -PathType Leaf)) {
        throw "bundletool is required for -Bundle. Set BUNDLETOOL_JAR to the official bundletool-all JAR path."
    }
    $Java = Join-Path $JavaHome "bin\java.exe"
    if (!(Test-Path -LiteralPath $Java -PathType Leaf)) {
        $Java = "java"
    }
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Gen, $Classes, $Dex, $Compiled, $ModuleRoot
Remove-Item -Force -ErrorAction SilentlyContinue `
    $Unsigned, $Aligned, $ProtoApk, $ModuleZip, $ProtoZip, $Apk, $Aab
New-Item -ItemType Directory -Force -Path $Out, $Gen, $Classes, $Dex, $Compiled | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "res\drawable") | Out-Null

Copy-Item -Force -LiteralPath (Join-Path $Repo "public\assets\icon-192.png") -Destination (Join-Path $Root "res\drawable\icon.png")

Invoke-Checked (Join-Path $BuildTools "aapt2.exe") @("compile", "--dir", (Join-Path $Root "res"), "-o", (Join-Path $Compiled "res.zip"))
Invoke-Checked (Join-Path $BuildTools "aapt2.exe") @(
    "link",
    "-I", $PlatformJar,
    "--manifest", (Join-Path $Root "AndroidManifest.xml"),
    "--java", $Gen,
    "--min-sdk-version", "23",
    "--target-sdk-version", "35",
    "--version-code", $VersionCode.ToString(),
    "--version-name", $VersionName,
    "-o", $Unsigned,
    (Join-Path $Compiled "res.zip")
)

if ($Bundle) {
    Invoke-Checked (Join-Path $BuildTools "aapt2.exe") @(
        "link",
        "--proto-format",
        "-I", $PlatformJar,
        "--manifest", (Join-Path $Root "AndroidManifest.xml"),
        "--min-sdk-version", "23",
        "--target-sdk-version", "35",
        "--version-code", $VersionCode.ToString(),
        "--version-name", $VersionName,
        "-o", $ProtoApk,
        (Join-Path $Compiled "res.zip")
    )
}

$JavaFiles = Get-ChildItem -Recurse -Filter *.java (Join-Path $Root "src"), $Gen | ForEach-Object { $_.FullName }
$JavacArgs = @("-encoding", "UTF-8", "--release", "8", "-classpath", $PlatformJar, "-d", $Classes) + $JavaFiles
Invoke-Checked (Join-Path $JavaHome "bin\javac.exe") $JavacArgs

$ClassFiles = Get-ChildItem -Recurse -Filter *.class $Classes | ForEach-Object { $_.FullName }
$D8Args = @("--min-api", "23", "--lib", $PlatformJar, "--output", $Dex) + $ClassFiles
Invoke-Checked (Join-Path $BuildTools "d8.bat") $D8Args
Invoke-Checked (Join-Path $BuildTools "aapt.exe") @("add", $Unsigned, "classes.dex") $Dex
Invoke-Checked (Join-Path $BuildTools "zipalign.exe") @("-f", "4", $Unsigned, $Aligned)

if ($Configuration -eq "debug") {
    if (!(Test-Path $KeyStore)) {
        Invoke-Checked (Join-Path $JavaHome "bin\keytool.exe") @(
            "-genkeypair",
            "-keystore", $KeyStore,
            "-storepass", $KeyStorePassword,
            "-keypass", $KeyPassword,
            "-alias", $KeyAlias,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-dname", "CN=Android Debug,O=Torah Pod,C=US"
        )
    }
}

$ApkSignerKeyStorePassword = if ($Configuration -eq "release") { "env:TORAH_POD_RELEASE_KEYSTORE_PASSWORD" } else { "pass:$KeyStorePassword" }
$ApkSignerKeyPassword = if ($Configuration -eq "release") { "env:TORAH_POD_RELEASE_KEY_PASSWORD" } else { "pass:$KeyPassword" }

Invoke-Checked (Join-Path $BuildTools "apksigner.bat") @(
    "sign",
    "--ks", $KeyStore,
    "--ks-key-alias", $KeyAlias,
    "--ks-pass", $ApkSignerKeyStorePassword,
    "--key-pass", $ApkSignerKeyPassword,
    "--out", $Apk,
    $Aligned
)

Invoke-Checked (Join-Path $BuildTools "apksigner.bat") @("verify", "--verbose", $Apk)
Write-Host "APK written to $Apk (version $VersionName, code $VersionCode, configuration $Configuration)"

if ($Bundle) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $ModuleRoot
    New-Item -ItemType Directory -Force -Path (Join-Path $ModuleRoot "manifest"), (Join-Path $ModuleRoot "dex") | Out-Null
    Remove-Item -Force -ErrorAction SilentlyContinue $ModuleZip, $Aab, $ProtoZip
    # APK files are ZIP archives, but Expand-Archive only accepts a .zip suffix.
    Copy-Item -Force -LiteralPath $ProtoApk -Destination $ProtoZip
    Expand-Archive -LiteralPath $ProtoZip -DestinationPath $ModuleRoot -Force
    Move-Item -Force -LiteralPath (Join-Path $ModuleRoot "AndroidManifest.xml") -Destination (Join-Path $ModuleRoot "manifest\AndroidManifest.xml")
    Copy-Item -Force -LiteralPath (Join-Path $Dex "classes.dex") -Destination (Join-Path $ModuleRoot "dex\classes.dex")
    # bundletool requires forward-slash entry names. Compress-Archive writes
    # Windows backslashes, so use the JDK JAR writer for the module ZIP.
    Invoke-Checked (Join-Path $JavaHome "bin\jar.exe") @("cMf", $ModuleZip, "-C", $ModuleRoot, ".")
    Invoke-Checked $Java @("-jar", $BundleTool, "build-bundle", "--modules=$ModuleZip", "--output=$Aab", "--overwrite")
    $JarSignerPasswordArguments = if ($Configuration -eq "release") {
        @("-storepass:env", "TORAH_POD_RELEASE_KEYSTORE_PASSWORD", "-keypass:env", "TORAH_POD_RELEASE_KEY_PASSWORD")
    } else {
        @("-storepass", $KeyStorePassword, "-keypass", $KeyPassword)
    }
    Invoke-Checked (Join-Path $JavaHome "bin\jarsigner.exe") (@(
        "-keystore", $KeyStore
    ) + $JarSignerPasswordArguments + @(
        $Aab
        $KeyAlias
    ))
    # Debug certificates are intentionally self-signed, which makes jarsigner
    # -strict return a non-zero exit code despite a valid signature.
    Invoke-Checked (Join-Path $JavaHome "bin\jarsigner.exe") @("-verify", $Aab)
    Invoke-Checked $Java @("-jar", $BundleTool, "validate", "--bundle=$Aab")
    Write-Host "Android App Bundle written to $Aab"
}
