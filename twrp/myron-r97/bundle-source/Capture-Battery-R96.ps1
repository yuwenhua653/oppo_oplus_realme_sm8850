$ErrorActionPreference = 'Stop'
$script:Root = $PSScriptRoot
$script:Adb = $null
$script:Report = $null
$script:Partial = $false
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8

function Quote-NativeArg([string]$Value) {
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Find-Adb {
    foreach ($candidate in @((Join-Path $Root 'adb.exe'), (Join-Path (Split-Path $Root -Parent) 'adb.exe'))) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $command = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw '找不到 adb.exe。请将平台工具中的 adb.exe、AdbWinApi.dll、AdbWinUsbApi.dll 放在本目录，或将平台工具加入 PATH。'
}


# Keep the proven R92 process invocation; timeout preserves completed streams only.
function Invoke-Adb([string[]]$Arguments, [int]$TimeoutSeconds = 15) {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $script:Adb
    $start.Arguments = (($Arguments | ForEach-Object { Quote-NativeArg $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
        if ($timedOut) { try { $process.Kill() } catch {} }
        [void]$process.WaitForExit(2000)
        try { [void]$stdout.Wait(1500) } catch {}
        try { [void]$stderr.Wait(1500) } catch {}
        $stdoutReady = $stdout.IsCompleted -and -not $stdout.IsFaulted -and -not $stdout.IsCanceled
        $stderrReady = $stderr.IsCompleted -and -not $stderr.IsFaulted -and -not $stderr.IsCanceled
        $out = if ($stdoutReady) { $stdout.Result } else { '[STDOUT_STREAM_INCOMPLETE: current stream text may be unavailable]' }
        $err = if ($stderrReady) { $stderr.Result } else { '[STDERR_STREAM_INCOMPLETE: current stream text may be unavailable]' }
        $exitCode = if ($timedOut) { 124 } elseif ($process.HasExited) { $process.ExitCode } else { 125 }
        return [pscustomobject]@{ ExitCode = $exitCode; Out = $out; Err = $err; TimedOut = $timedOut; StreamsComplete = ($stdoutReady -and $stderrReady) }
    } finally { $process.Dispose() }
}

function Require-AdbSuccess($Result, [string]$Operation) {
    if ($Result.ExitCode -ne 0 -or -not $Result.StreamsComplete) {
        throw ($Operation + '失败或超时，请保持手机连接并允许 USB 调试。')
    }
}

function Get-OneDevice {
    $result = Invoke-Adb -Arguments @('devices')
    Require-AdbSuccess $result '检查设备'
    $devices = @()
    foreach ($line in ($result.Out -split '\r?\n')) {
        $line = $line.Trim()
        if ($line -eq '' -or $line -eq 'List of devices attached' -or $line.StartsWith('* daemon')) { continue }
        if ($line -match '^([^\s]+)\s+(.+)$') {
            $devices += [pscustomobject]@{ Id = $Matches[1]; State = $Matches[2].Trim() }
        } else { throw 'ADB 返回了无法识别的设备记录，已停止。' }
    }
    if ($devices.Count -ne 1 -or $devices[0].State -notin @('device','recovery')) {
        throw '需要且只能连接一台 ADB 状态为 recovery 或 device 的手机。'
    }
    if ($devices[0].Id -notmatch '^[A-Za-z0-9._:-]+$') { throw '设备标识格式异常，已停止。' }
    return $devices[0].Id
}

function Add-Report([string]$Text) {
    [IO.File]::AppendAllText($script:Report, $Text, $utf8)
}


try {
    $resultRoot = Join-Path $Root 'results'
    [void][IO.Directory]::CreateDirectory($resultRoot)
    $script:Report = Join-Path $resultRoot ('r96-battery-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8) + '.txt')
    [IO.File]::WriteAllText($script:Report, "R96_BATTERY_CAPTURE_BEGIN`r`n", $utf8)
    $script:Adb = Find-Adb
    Write-Host '请在刷入 R96 并进入 Android 后采集；本工具不会重启、刷机或更改电池状态。'
    $serial = Get-OneDevice
    $checks = @(
        @('identity', 'date; uname -r; cat /proc/sys/kernel/random/boot_id; cat /proc/uptime; getprop ro.bootmode; getprop ro.boot.force_normal_boot; getprop init.svc.recovery; getprop vendor.all.modules.ready; getprop init.svc.vendor.health-default; getprop sys.r95.ui.ready'),
        @('mca_status', 'head -c 8192 /vendor_dlkm/r36-report/r92-mca.status'),
        @('mca_start_log', 'head -c 131072 /vendor_dlkm/r36-report/r92-mca.log'),
        @('normal_handoff', 'head -c 131072 /vendor_dlkm/r36-report/probe.log'),
        @('framework_battery', 'dumpsys battery'),
        @('battery_nodes', 'for p in /sys/class/power_supply/battery /sys/class/power_supply/usb /sys/class/power_supply/bms; do echo NODE=$p; readlink -f "$p"; for a in type present status capacity voltage_now current_now temp health; do echo ATTRIBUTE=$a; /system/bin/toybox timeout -k 1 1 /system/bin/toybox head -c 256 "$p/$a"; echo READ_STATUS=$?; done; done'),
        @('driver_bindings', 'for p in /sys/bus/platform/devices/soc:mca*/driver /sys/bus/platform/devices/soc:strategy-fg/driver /sys/bus/i2c/devices/5-0055/driver /sys/bus/i2c/devices/5-006e/driver; do echo BINDING=$p; readlink -f "$p"; echo READ_STATUS=$?; done'),
        @('module_state', 'cat /proc/modules'),
        @('kernel_log', 'dmesg'),
        @('kernel_logcat', 'logcat -d -b kernel -t 2000 -v threadtime'),
        @('android_power_log', 'logcat -d -b all -t 1800 -v threadtime -s healthd BatteryService BatteryStatsService HealthServiceWrapper android.hardware.health-service.qti'),
        @('recovery_loader', 'head -c 65536 /tmp/r95-ui-loader.log'),
        @('haptic_inputs', 'cat /proc/bus/input/devices'),
        @('mca_status_end', 'head -c 8192 /vendor_dlkm/r36-report/r92-mca.status')
    )
    foreach ($check in $checks) {
        Write-Host ('读取 ' + $check[0])
        $r = Invoke-Adb -Arguments @('-s', $serial, 'shell', '-T', $check[1]) -TimeoutSeconds 20
        Add-Report ("`r`nSECTION " + $check[0] + "`r`n" + $r.Out + "`r`nSTDERR`r`n" + $r.Err + "`r`nEXIT=" + $r.ExitCode + " STREAMS_COMPLETE=" + $r.StreamsComplete + "`r`n")
        if ($r.ExitCode -ne 0 -or -not $r.StreamsComplete) { $script:Partial = $true }
    }
    Add-Report ("`r`nHOST_PARTIAL=" + $script:Partial + "`r`nR96_BATTERY_CAPTURE_END`r`n")
    Write-Host '请回传以下 TXT；部分日志也有用：'
    Write-Host $script:Report
} catch {
    if ($script:Report) { Add-Report ("`r`nHOST_ERROR=" + $_.Exception.Message + "`r`n") }
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($script:Report) { Write-Host $script:Report }
    exit 1
}
