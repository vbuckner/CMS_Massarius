# Creates (or replaces) the Windows scheduled task that runs scan.py every day.
# The times and the days back come from config\settings.json (scheduleTimes, days); change them there and run this again:
#     powershell -ExecutionPolicy Bypass -File scripts\schedule_scan.ps1
# Remove the task:  Unregister-ScheduledTask -TaskName "CMS Massarius scan" -Confirm:$false

$TaskName = "CMS Massarius scan"
$Root     = Split-Path $PSScriptRoot -Parent
$Settings = Get-Content (Join-Path $Root "config\settings.json") -Raw | ConvertFrom-Json
$Pythonw  = "C:\Python\python314\pythonw.exe"      # pythonw = no console window pops up
$Script   = Join-Path $Root "scan.py"
$Log      = Join-Path $Root "logs\scan.log"

# The old task from the claude_playground test folder is replaced by this one.
Unregister-ScheduledTask -TaskName "Massarius CMS email reader" -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`" --source schedule --log `"$Log`"" -WorkingDirectory $Root
$triggers = $Settings.scheduleTimes | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
# Runs as you, only while you are logged on (it needs your Outlook session).
# A run missed because the PC was off or asleep starts as soon as it is back.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settingsSet = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settingsSet `
    -Description "Scans the mailboxes in config\settings.json into cms_db and tags the new emails (CMS_Massarius\scan.py)" -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
