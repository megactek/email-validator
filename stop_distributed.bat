@echo off
setlocal enabledelayedexpansion

REM Stop all distributed validation processes
REM Usage: stop_distributed.bat output_dir

if "%~1"=="" (
    echo Usage: %0 ^<output_dir^>
    exit /b 1
)

set OUTPUT_DIR=%~1

REM Check if output directory exists
if not exist "%OUTPUT_DIR%" (
    echo Error: Output directory %OUTPUT_DIR% does not exist.
    exit /b 1
)

echo Stopping all validation clients...

REM Method 1: Try using stored PIDs
set FOUND_PIDS=0
for /f "delims=" %%f in ('dir /b "%OUTPUT_DIR%\pid_*.pid" 2^>nul') do (
    set PID_FILE=%OUTPUT_DIR%\%%f
    if exist "!PID_FILE!" (
        for /f %%p in ('type "!PID_FILE!"') do (
            echo Stopping process with PID %%p
            taskkill /PID %%p /F /T 2>nul
            if !errorlevel! equ 0 (
                echo Process stopped successfully
                set FOUND_PIDS=1
            )
        )
    )
)

REM Method 2: If no PIDs found or couldn't kill them, try to kill related processes
if %FOUND_PIDS% equ 0 (
    echo No valid PID files found, trying to stop relevant processes...
    
    echo Stopping Python processes related to email validation...
    for /f "tokens=2" %%p in ('tasklist /fi "imagename eq python.exe" /nh ^| findstr "python"') do (
        echo Stopping Python process with PID %%p
        taskkill /PID %%p /F 2>nul
    )
    
    echo Stopping related CMD processes...
    for /f "tokens=2" %%p in ('tasklist /fi "imagename eq cmd.exe" /nh ^| findstr "cmd"') do (
        echo Stopping CMD process with PID %%p
        taskkill /PID %%p /F 2>nul
    )
)

REM Clean up temporary command files
echo Cleaning up temporary files...
del "%TEMP%\run_client_*.cmd" 2>nul

echo.
echo All validation clients stopped.
echo.
echo You might want to check if any processes are still running:
echo tasklist /fi "imagename eq python.exe"
echo tasklist /fi "imagename eq cmd.exe"
echo.
echo To forcefully kill all Python processes if needed:
echo taskkill /f /im python.exe

endlocal