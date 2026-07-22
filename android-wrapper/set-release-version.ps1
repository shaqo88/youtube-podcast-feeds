[CmdletBinding(DefaultParameterSetName = "Bump", SupportsShouldProcess)]
param(
    [Parameter(ParameterSetName = "Bump")]
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch",

    [Parameter(Mandatory, ParameterSetName = "Explicit")]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$VersionName,

    [Parameter(ParameterSetName = "Explicit")]
    [ValidateRange(1, 2100000000)]
    [int]$VersionCode,

    [Parameter(Mandatory, ParameterSetName = "Check")]
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$VersionFile = Join-Path $PSScriptRoot "release-version.json"
$Current = Get-Content -Raw -LiteralPath $VersionFile | ConvertFrom-Json

if ($null -eq $Current.versionName -or $null -eq $Current.versionCode) {
    throw "$VersionFile must contain versionName and versionCode."
}
if ([string]$Current.versionName -notmatch '^\d+\.\d+\.\d+$') {
    throw "Current versionName must use stable semantic versioning (major.minor.patch)."
}

$CurrentCode = [int64]$Current.versionCode
if ($CurrentCode -lt 1 -or $CurrentCode -gt 2100000000) {
    throw "Current versionCode is outside the supported Android range."
}

$CurrentSemVer = [version]$Current.versionName
if ($Check) {
    Write-Host "Android release identity is valid: $($Current.versionName) ($CurrentCode)"
    return
}

if ($PSCmdlet.ParameterSetName -eq "Bump") {
    $NextVersion = switch ($Bump) {
        "major" { [version]::new($CurrentSemVer.Major + 1, 0, 0) }
        "minor" { [version]::new($CurrentSemVer.Major, $CurrentSemVer.Minor + 1, 0) }
        default { [version]::new($CurrentSemVer.Major, $CurrentSemVer.Minor, $CurrentSemVer.Build + 1) }
    }
    $VersionName = $NextVersion.ToString(3)
    $VersionCode = [int]($CurrentCode + 1)
} else {
    if (!$PSBoundParameters.ContainsKey("VersionCode")) {
        $VersionCode = [int]($CurrentCode + 1)
    }
    if ([version]$VersionName -le $CurrentSemVer) {
        throw "VersionName must be greater than the current $($Current.versionName)."
    }
    if ($VersionCode -le $CurrentCode) {
        throw "VersionCode must be greater than the current $CurrentCode."
    }
}

$Next = [ordered]@{
    versionName = $VersionName
    versionCode = $VersionCode
}

if ($PSCmdlet.ShouldProcess($VersionFile, "Set Android release to $VersionName ($VersionCode)")) {
    $Json = $Next | ConvertTo-Json
    Set-Content -LiteralPath $VersionFile -Value $Json -Encoding utf8
    Write-Host "Android release advanced: $($Current.versionName) ($CurrentCode) -> $VersionName ($VersionCode)"
}
