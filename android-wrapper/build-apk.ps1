param(
    [string]$Configuration = "debug"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Root
$Scoop = Join-Path $env:USERPROFILE "scoop\apps"
$AndroidHome = Join-Path $Scoop "android-clt\current"
$JavaHome = Join-Path $Scoop "openjdk\26-35"
$BuildTools = Join-Path $AndroidHome "build-tools\35.0.0"
$PlatformJar = Join-Path $AndroidHome "platforms\android-35\android.jar"
$Out = Join-Path $Root "build"
$Gen = Join-Path $Out "gen"
$Classes = Join-Path $Out "classes"
$Dex = Join-Path $Out "dex"
$Compiled = Join-Path $Out "compiled"
$Unsigned = Join-Path $Out "torah-pod-unsigned.apk"
$Aligned = Join-Path $Out "torah-pod-aligned.apk"
$Apk = Join-Path $Out "torah-pod-$Configuration.apk"
$KeyStore = Join-Path $Out "debug.keystore"
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

if (!(Test-Path $PlatformJar)) {
    throw "Android platform android-35 is missing at $PlatformJar"
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Gen, $Classes, $Dex, $Compiled
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
    "--version-code", "1",
    "--version-name", "0.1.0",
    "-o", $Unsigned,
    (Join-Path $Compiled "res.zip")
)

$JavaFiles = Get-ChildItem -Recurse -Filter *.java (Join-Path $Root "src"), $Gen | ForEach-Object { $_.FullName }
$JavacArgs = @("-encoding", "UTF-8", "-source", "8", "-target", "8", "-classpath", $PlatformJar, "-d", $Classes) + $JavaFiles
Invoke-Checked (Join-Path $JavaHome "bin\javac.exe") $JavacArgs

$ClassFiles = Get-ChildItem -Recurse -Filter *.class $Classes | ForEach-Object { $_.FullName }
$D8Args = @("--min-api", "23", "--lib", $PlatformJar, "--output", $Dex) + $ClassFiles
Invoke-Checked (Join-Path $BuildTools "d8.bat") $D8Args
Invoke-Checked (Join-Path $BuildTools "aapt.exe") @("add", $Unsigned, "classes.dex") $Dex
Invoke-Checked (Join-Path $BuildTools "zipalign.exe") @("-f", "4", $Unsigned, $Aligned)

if (!(Test-Path $KeyStore)) {
    Invoke-Checked (Join-Path $JavaHome "bin\keytool.exe") @(
        "-genkeypair",
        "-keystore", $KeyStore,
        "-storepass", "android",
        "-keypass", "android",
        "-alias", "androiddebugkey",
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-dname", "CN=Android Debug,O=Torah Pod,C=US"
    )
}

Invoke-Checked (Join-Path $BuildTools "apksigner.bat") @(
    "sign",
    "--ks", $KeyStore,
    "--ks-pass", "pass:android",
    "--key-pass", "pass:android",
    "--out", $Apk,
    $Aligned
)

Invoke-Checked (Join-Path $BuildTools "apksigner.bat") @("verify", "--verbose", $Apk)
Write-Host "APK written to $Apk"
