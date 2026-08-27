# Run the recompiled game for a few seconds and photograph its window.
#   scripts\shot.ps1 [-Seconds 6] [-Out work\shot.png]
param([int]$Seconds = 6, [string]$Out = "work\shot.png")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Shot {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$env:NEP_QUIET_BRIDGES = "1"
$env:NEP_NO_DIALOGS = "1"
Remove-Item Env:NEP_WATCHDOG_MS -ErrorAction SilentlyContinue

$p = Start-Process -FilePath "work\neptune.exe" `
                   -ArgumentList "original\ONWINCD\ONWIN32.EXE" `
                   -PassThru -RedirectStandardError "work\shot.log" -RedirectStandardOutput "work\shot.out"
Start-Sleep -Seconds $Seconds

# FindWindow by class name does not work here: window classes are per-process,
# and the game runs in the relaunched child (see premap.c). Enumerate instead
# and keep the first top-level window belonging to any neptune.exe.
$pids = @(Get-Process neptune -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$hwnd = [IntPtr]::Zero
$cb = [Shot+EnumProc]{
    param($h, $lp)
    $pid2 = 0
    [void][Shot]::GetWindowThreadProcessId($h, [ref]$pid2)
    if ($pids -contains $pid2 -and $script:hwnd -eq [IntPtr]::Zero) { $script:hwnd = $h }
    return $true
}
[void][Shot]::EnumWindows($cb, [IntPtr]::Zero)

if ($hwnd -eq [IntPtr]::Zero) {
    Write-Output "no window for pids: $($pids -join ',')"
} else {
    $r = New-Object Shot+RECT
    [void][Shot]::GetWindowRect($hwnd, [ref]$r)
    $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
    Write-Output "window ${w}x${h} at $($r.Left),$($r.Top)"
    if ($w -gt 0 -and $h -gt 0) {
        $bmp = New-Object System.Drawing.Bitmap($w, $h)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $hdc = $g.GetHdc()
        [void][Shot]::PrintWindow($hwnd, $hdc, 2)
        $g.ReleaseHdc($hdc)
        $bmp.Save((Join-Path $root $Out), [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        Write-Output "wrote $Out"
    }
}
$p | Stop-Process -Force -ErrorAction SilentlyContinue
