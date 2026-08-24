<#!
Keeps the local dashboard address available at http://127.0.0.1:8000.

Windows Task Scheduler starts this script when the current user signs in. If
the Pi reboots or the network drops, SSH exits and this loop reconnects after
five seconds. The tunnel stays local to this Windows computer.
#>

$ErrorActionPreference = "Continue"
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$log = Join-Path $PSScriptRoot "dashboard-tunnel.log"

while ($true) {
    "$(Get-Date -Format s) starting tunnel" | Add-Content -Path $log
    & $ssh -N -L "8000:127.0.0.1:8000" `
        -o "ExitOnForwardFailure=yes" `
        -o "ServerAliveInterval=30" `
        -o "ServerAliveCountMax=3" `
        "raspberrypi@puzzle-rig-pi" 2>&1 | Add-Content -Path $log
    "$(Get-Date -Format s) tunnel stopped; retrying in 5 seconds" | Add-Content -Path $log
    Start-Sleep -Seconds 5
}
