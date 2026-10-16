param([ValidateSet('test-20261015-maps','test-20261015-chat','test-20261016-store-item','test-20261016-commands','test-20261016-discovery','test-20261016-window','test-20261016-complete')][string]$TestPackage = 'test-20261015-maps')
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$package = Join-Path $workspace ('client_patch\' + $TestPackage)
$plan = Get-Content -LiteralPath (Join-Path $package 'install-plan.json') -Raw | ConvertFrom-Json
$verified = Get-Content -LiteralPath (Join-Path $package 'restore-verification.json') -Raw | ConvertFrom-Json
$expectedPackage = switch ($TestPackage) { 'test-20261016-complete' { 'full-draft-2968c78ffe29cee7' } 'test-20261016-window' { 'full-draft-45f998a2ad1f82ea' } 'test-20261016-discovery' { 'full-draft-1f21b7a124c7059b' } 'test-20261016-commands' { 'full-draft-1f21b7a124c7059b' } 'test-20261016-store-item' { 'full-draft-bf681ae09630df99' } 'test-20261015-chat' { 'full-draft-b38987d4c23ab456' } default { 'full-draft-e93bb5ed8e8cd5c1' } }
if ($plan.package_id -ne $expectedPackage -or $verified.state -ne 'restored') { throw 'Unverified restoration' }
$pluginReceipt = Join-Path $package 'plugin-installation\extras-receipt.json'
if ((Test-Path -LiteralPath $pluginReceipt) -and ((Get-Content -LiteralPath $pluginReceipt -Raw | ConvertFrom-Json).state -ne 'restored')) { throw 'Restore the plugin before cleanup' }
foreach ($archive in $plan.archives) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $verified.game_directory $archive.name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $archive.original_sha256) { throw "Game original changed: $($archive.name)" }
}
# Rebind source reads before removing the now-redundant backups.
$configPath = Join-Path $workspace 'data\original-archives.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config.PSObject.Properties.Remove('source_backup_directory')
$config.note = '游戏已还原并核对五个英文原件；后续构建只读使用游戏英文资源。测试备份已按用户要求删除。'
$config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding utf8
$targets = @()
foreach ($archive in $plan.archives) {
    $targets += Join-Path $package ('backups\' + $archive.name + '.original')
    $targets += Join-Path $package $archive.candidate
}
$buildData = Join-Path $package 'build-data'
if (Test-Path -LiteralPath $buildData) { $targets += @(Get-ChildItem -LiteralPath $buildData -File -Filter '*.pack' | ForEach-Object { $_.FullName }) }
$removed = @()
foreach ($target in $targets) {
    $absolute = [IO.Path]::GetFullPath($target)
    if (-not $absolute.StartsWith($package + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup path outside test package' }
    if (Test-Path -LiteralPath $absolute) {
        $item = Get-Item -LiteralPath $absolute
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected cleanup target' }
        $removed += @{path=$absolute; bytes=$item.Length}
        Remove-Item -LiteralPath $absolute
    }
}
$record = @{state='restored-and-cleaned'; package_id=$plan.package_id; freed_bytes=($removed | Measure-Object -Property bytes -Sum).Sum; deleted=$removed; game_originals_verified=5; deployment_enabled=$false; completed_utc=[DateTime]::UtcNow.ToString('o')}
$record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $package 'disk-cleanup.json') -Encoding utf8
$record | Select-Object state, freed_bytes, game_originals_verified | ConvertTo-Json
