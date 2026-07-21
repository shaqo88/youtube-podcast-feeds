$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$JavaHome = @(
    $env:JAVA_HOME,
    (Join-Path $env:USERPROFILE "scoop\apps\openjdk\26-35")
) | Where-Object {
    $_ -and (Test-Path -LiteralPath (Join-Path $_ "bin\javac.exe")) -and (Test-Path -LiteralPath (Join-Path $_ "bin\java.exe"))
} | Select-Object -First 1

if (!$JavaHome) {
    throw "Java 8+ is required. Set JAVA_HOME or install the documented JDK."
}

$Javac = Join-Path $JavaHome "bin\javac.exe"
$Java = Join-Path $JavaHome "bin\java.exe"
$Out = Join-Path $Root "build\bridge-policy-test"

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Out
New-Item -ItemType Directory -Force -Path $Out | Out-Null
& $Javac -encoding UTF-8 -d $Out `
    (Join-Path $Root "src\com\torahpod\app\NativeBridgePolicy.java") `
    (Join-Path $Root "test\com\torahpod\app\NativeBridgePolicyTest.java")
if ($LASTEXITCODE -ne 0) { throw "Bridge policy test compilation failed." }
& $Java -cp $Out com.torahpod.app.NativeBridgePolicyTest
if ($LASTEXITCODE -ne 0) { throw "Bridge policy test failed." }
