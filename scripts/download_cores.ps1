$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$coreDir = Join-Path $root "core\bin"
$downloadDir = Join-Path $root "cache\downloads"
New-Item -ItemType Directory -Force -Path $coreDir, $downloadDir | Out-Null

function Get-GitHubLatestAsset {
    param(
        [Parameter(Mandatory=$true)][string]$Repository,
        [Parameter(Mandatory=$true)][string]$AssetPattern,
        [Parameter(Mandatory=$true)][string]$Prefix
    )

    $headers = @{
        "User-Agent" = "LuckasApp-CoreDownloader"
        "Accept" = "application/vnd.github+json"
    }
    $releaseTag = "cached"
    $assetName = ""
    $zipPath = $null
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repository/releases/latest" -Headers $headers
        $asset = $release.assets | Where-Object { $_.name -match $AssetPattern } | Select-Object -First 1
        if (-not $asset) {
            throw "No asset matching $AssetPattern found for $Repository"
        }
        $releaseTag = $release.tag_name
        $assetName = $asset.name
        $zipPath = Join-Path $downloadDir $asset.name
        Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $zipPath
    } catch {
        $cached = Get-ChildItem -LiteralPath $downloadDir -File -Filter "*.zip" |
            Where-Object { $_.Name -match $AssetPattern } |
            Select-Object -First 1
        if (-not $cached) {
            throw
        }
        Write-Warning "Using cached $($cached.Name) for $Repository because GitHub API/download failed: $($_.Exception.Message)"
        $assetName = $cached.Name
        $zipPath = $cached.FullName
    }

    $extractPath = Join-Path $downloadDir $Prefix
    if (Test-Path -LiteralPath $extractPath) {
        Remove-Item -LiteralPath $extractPath -Recurse -Force
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force

    Get-ChildItem -LiteralPath $extractPath -Recurse -File |
        Where-Object { $_.Name -in @("geoip.dat", "geosite.dat") } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $coreDir $_.Name) -Force }

    $targetMap = @{
        "gxray.exe" = "xray.exe"
        "gv2ray.exe" = "v2ray.exe"
        "xray.exe" = "xray.exe"
        "v2ray.exe" = "v2ray.exe"
    }
    $copiedTargets = @{}
    Get-ChildItem -LiteralPath $extractPath -Recurse -File -Force |
        Where-Object { $targetMap.ContainsKey($_.Name) -and $_.Length -gt 2000000 } |
        Sort-Object Length -Descending |
        ForEach-Object {
            $targetName = $targetMap[$_.Name]
            if ($copiedTargets.ContainsKey($targetName)) {
                return
            }
            $versionOutput = ""
            try {
                $versionOutput = (& $_.FullName version 2>&1 | Out-String).Trim()
            } catch {
                $versionOutput = ""
            }
            if ($versionOutput) {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $coreDir $targetName) -Force
                $copiedTargets[$targetName] = $true
            } else {
                Write-Warning "Skipped $($_.Name) from $Repository because version output was empty."
            }
        }

    [PSCustomObject]@{
        Repository = $Repository
        Tag = $releaseTag
        Asset = $assetName
        DownloadedTo = $zipPath
    }
}

$xray = Get-GitHubLatestAsset -Repository "XTLS/Xray-core" -AssetPattern "^Xray-windows-64\.zip$" -Prefix "xray"
$v2ray = Get-GitHubLatestAsset -Repository "v2fly/v2ray-core" -AssetPattern "^v2ray-windows-64\.zip$" -Prefix "v2ray"

$xray
$v2ray
Get-ChildItem -LiteralPath $coreDir -File | Select-Object Name,Length
