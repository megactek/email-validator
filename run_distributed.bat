@echo off
setlocal enabledelayedexpansion

REM Run distributed email validation across multiple servers
REM Usage: run_distributed.bat input_file output_dir server1:port1,server2:port2,server3:port3

if "%~3"=="" (
    echo Usage: %0 ^<input_file^> ^<output_dir^> ^<server1:port1,server2:port2,...^> [workers_per_server] [batch_size]
    exit /b 1
)

set INPUT_FILE=%~1
set OUTPUT_DIR=%~2
set SERVERS=%~3
set WORKERS_PER_SERVER=5
set BATCH_SIZE=100

if not "%~4"=="" set WORKERS_PER_SERVER=%~4
if not "%~5"=="" set BATCH_SIZE=%~5

REM Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Count total lines in input file
set /a TOTAL_LINES=0
for /f %%a in ('type "%INPUT_FILE%" ^| find /c /v ""') do set TOTAL_LINES=%%a

REM Count number of servers
set SERVER_COUNT=0
for %%a in (%SERVERS:,= %) do set /a SERVER_COUNT+=1

REM Calculate lines per server
set /a LINES_PER_SERVER=%TOTAL_LINES% / %SERVER_COUNT% + 1

echo Splitting input file into chunks...

REM Use PowerShell to split the file
powershell -Command "$lines = Get-Content '%INPUT_FILE%'; $serverCount = %SERVER_COUNT%; $linesPerServer = %LINES_PER_SERVER%; for ($i=0; $i -lt $serverCount; $i++) { $start = $i * $linesPerServer; $end = [Math]::Min(($i+1) * $linesPerServer - 1, $lines.Length-1); $lines[$start..$end] | Out-File '%OUTPUT_DIR%\chunk_$i.txt' -Encoding utf8 }"

echo Starting clients for each server...

REM Convert comma-separated list to array
set i=0
for %%s in (%SERVERS:,= %) do (
    set SERVER_ARRAY[!i!]=%%s
    set /a i+=1
)

REM Get all chunk files
set i=0
for /f "delims=" %%f in ('dir /b "%OUTPUT_DIR%\chunk_*.txt"') do (
    set CHUNK_FILES[!i!]=%%f
    set /a i+=1
)

REM Start a client for each server
set /a SERVER_COUNT-=1
for /l %%i in (0,1,%SERVER_COUNT%) do (
    set INDEX=%%i
    set SERVER=!SERVER_ARRAY[%%i]!
    set CHUNK=%OUTPUT_DIR%\!CHUNK_FILES[%%i]!
    set OUTPUT_PREFIX=%OUTPUT_DIR%\result_!CHUNK_FILES[%%i]!
    
    echo Starting client for server !SERVER! with chunk !CHUNK!
    
    REM Run in background using start command
    start /b python client/email_validator_client.py "!CHUNK!" "!OUTPUT_PREFIX!" ^
        --servers "!SERVER!" ^
        --max-workers "%WORKERS_PER_SERVER%" ^
        --batch-size "%BATCH_SIZE%" ^
        --retry-limit 3 ^
        --timeout 30 > "%OUTPUT_DIR%\log_!CHUNK_FILES[%%i]!.log" 2>&1
    
    REM Store the process ID (not as straightforward in Windows)
    for /f "tokens=2" %%p in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID"') do (
        echo %%p > "%OUTPUT_DIR%\pid_!CHUNK_FILES[%%i]!.pid"
        goto :done_%%i
    )
    :done_%%i
    
    REM Sleep to avoid all clients starting at exactly the same time
    timeout /t 2 /nobreak > nul
)

echo All clients started. Monitor progress with:
echo type %OUTPUT_DIR%\log_*.log
echo.
echo To stop all clients:
echo stop_distributed.bat %OUTPUT_DIR%

endlocal