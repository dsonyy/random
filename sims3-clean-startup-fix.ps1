# sims3-clean-startup-fix.ps1 - clean start for The Sims 3 (EA App version)
# 1. Cleans the game's user folder in Documents, keeping saves, settings and everything
#    the player created or installed. Removed items are moved to "The Sims 3_lastcleanup"
#    (only the most recent cleanup is kept there).
# 2. Starts the game launcher.

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'sims3-clean-startup-fix'

$docs     = [Environment]::GetFolderPath('MyDocuments')
$root     = Join-Path $docs 'Electronic Arts\The Sims 3'
$snapshot = Join-Path $docs 'Electronic Arts\The Sims 3_lastcleanup'
# Kept: saves, settings and everything the player created or installed
$keep     = @('Saves', 'Options.ini', 'Mods', 'Library', 'Screenshots', 'Recorded Videos',
              'Custom Music', 'SavedOutfits', 'SavedSims', 'Exports',
              'Collections', 'Downloads', 'InstalledWorlds', 'DCBackup', 'DCCache')
$gameProcs = 'TS3', 'TS3W', 'Sims3Launcher', 'Sims3LauncherW'

function Say($msg) { Write-Host "[$(Get-Date -Format HH:mm:ss)] $msg" }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; Read-Host 'Press Enter to close'; exit 1 }

try {
    if (Get-Process $gameProcs -ErrorAction SilentlyContinue) { Fail 'The game or its launcher is already running. Close it and run this script again.' }

    # EA App install location (from the registry)
    $installDir = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Sims\The Sims 3' -ErrorAction SilentlyContinue).'Install Dir'
    if (-not $installDir) { Fail 'The Sims 3 (EA App) installation was not found in the registry.' }
    $launcher = Join-Path $installDir 'Game\Bin\Sims3Launcher.exe'
    if (-not (Test-Path $launcher)) { Fail "File not found: $launcher" }

    # 1. Cleanup
    if (Test-Path $root) {
        Say 'Cleaning the game folder in Documents...'
        if (Test-Path $snapshot) { Remove-Item $snapshot -Recurse -Force }
        New-Item -ItemType Directory -Path $snapshot | Out-Null
        $moved = 0
        Get-ChildItem $root -Force | Where-Object { $keep -notcontains $_.Name } | ForEach-Object {
            Move-Item $_.FullName (Join-Path $snapshot $_.Name)
            $moved++
        }
        Say "Moved $moved items to 'The Sims 3_lastcleanup'. Saves, settings and your content were kept."
    }

    # 2. Start the game
    Say 'Starting The Sims 3...'
    Start-Process $launcher -WorkingDirectory (Split-Path $launcher)
    Start-Sleep -Seconds 3
}
catch {
    Fail $_.Exception.Message
}
