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

REM Kill processes by PIDs stored in pid files
for /f "delims=" %%f in ('dir /b "%OUTPUT_DIR%\pid_*.pid"') do (
    set PID_FILE=%OUTPUT_DIR%\%%f
    for /f %%p in ('type "!PID_FILE!"') do (
        echo Stopping process with PID %%p
        taskkill /PID %%p /F 2>nul
        if !errorlevel! equ 0 (
            echo Process stopped successfully
        ) else (
            echo Process already stopped or not found
        )
    )
)

echo All validation clients stopped.
endlocal