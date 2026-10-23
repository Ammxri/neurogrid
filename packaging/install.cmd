@echo off
rem NeuroGrid offline installer (Windows): starts install.ps1 with Windows PowerShell 5.1. The execution
rem policy is relaxed for this one process only; no system setting is changed. Options: see install.ps1.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
exit /b %ERRORLEVEL%
