param(
    [string]$RuntimePython = (Join-Path $env:USERPROFILE '.cache\caelestia-windows\runtime\Scripts\python.exe')
)
$ErrorActionPreference = 'Stop'
$taskSource = [IO.Path]::GetFullPath($PSScriptRoot)
$taskBuild = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE '.cache\caelestia-windows\build'))
$taskDistParent = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CaelestiaWindows'))
$taskDist = [IO.Path]::GetFullPath((Join-Path $taskDistParent 'app'))
$taskMarker = Join-Path $taskDist '.caelestia-windows-package'

if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
    throw "Python runtime not found: $RuntimePython. Create a short-path venv, install requirements.txt and PyInstaller, then pass -RuntimePython."
}
if ($taskDist -ne ([IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CaelestiaWindows\app')))) {
    throw 'Unexpected package target; refusing to replace it.'
}
if (Test-Path -LiteralPath $taskDist) {
    $taskDir = Get-Item -LiteralPath $taskDist
    if (($taskDir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Package target is a link; refusing to replace it.'
    }
    $taskHasFiles = @(Get-ChildItem -LiteralPath $taskDist -Force).Count -gt 0
    if ($taskHasFiles -and -not (Test-Path -LiteralPath $taskMarker -PathType Leaf)) {
        throw 'Target contains files without our package marker; refusing to replace it.'
    }
    if (Test-Path -LiteralPath $taskMarker) {
        if ((Get-Content -LiteralPath $taskMarker -Raw).Trim() -ne 'CaelestiaWindows portable app v1') {
            throw 'Package marker is not recognized; refusing to replace it.'
        }
    }
}
$taskExe = Join-Path $taskDist 'CaelestiaWindows.exe'
$taskRunning = @(Get-Process -Name CaelestiaWindows -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskExe })
if ($taskRunning.Count) { throw 'Exit the packaged app from its tray menu before rebuilding.' }
New-Item -ItemType Directory -Path $taskBuild -Force | Out-Null
New-Item -ItemType Directory -Path $taskDistParent -Force | Out-Null
$env:CAELESTIA_BUILD_DIR = $taskBuild
$taskOriginalPath = $env:PATH
try {
    # Avoid collecting a different program's same-named ICU/OpenSSL DLLs.
    $env:PATH = @((Split-Path -Parent $RuntimePython), (Join-Path $env:SystemRoot 'System32'), $env:SystemRoot) -join ';'
    & $RuntimePython -m PyInstaller --noconfirm --workpath $taskBuild --distpath $taskDistParent (Join-Path $taskSource 'CaelestiaWindows.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
}
finally {
    $env:PATH = $taskOriginalPath
}
Set-Content -LiteralPath $taskMarker -Value 'CaelestiaWindows portable app v1' -Encoding UTF8

# Keep readable documentation and corresponding application sources beside the
# executable. Qt/Python/dependency DLLs remain dynamically loaded in _internal.
foreach ($taskDoc in @('README.md','THIRD_PARTY_NOTICES.md','PRIVACY.md','LICENSE')) {
    Copy-Item -LiteralPath (Join-Path $taskSource $taskDoc) -Destination $taskDist -Force
}
$taskSourceCopy = Join-Path $taskDist 'source'
New-Item -ItemType Directory -Path $taskSourceCopy -Force | Out-Null
foreach ($taskName in @('main.py','backend.py','media_state.py','lyrics.py','artwork.py','http_client.py','wallpaper.py','weather_config.py','shape_geometry.py','gaming.py','prepare_assets.py','requirements.txt','settings.example.json','PRIVACY.md','CaelestiaWindows.spec','build.ps1','DESIGN.md','README.md','THIRD_PARTY_NOTICES.md','LICENSE')) {
    $taskFrom = Join-Path $taskSource $taskName
    if (Test-Path -LiteralPath $taskFrom) {
        Copy-Item -LiteralPath $taskFrom -Destination $taskSourceCopy -Force
    }
}
foreach ($taskFolder in @('qml','assets')) {
    Copy-Item -LiteralPath (Join-Path $taskSource $taskFolder) -Destination $taskSourceCopy -Recurse -Force
}
Write-Host "Portable app ready: $taskExe"
Write-Host 'Launch testing is required after building.'
