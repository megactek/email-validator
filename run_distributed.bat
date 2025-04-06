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
echo Total lines in input file: %TOTAL_LINES%

REM Count number of servers
set SERVER_COUNT=0
for %%a in (%SERVERS:,= %) do set /a SERVER_COUNT+=1
echo Number of servers: %SERVER_COUNT%

REM Calculate lines per server
set /a LINES_PER_SERVER=%TOTAL_LINES% / %SERVER_COUNT% + 1
echo Lines per server: %LINES_PER_SERVER%

echo Splitting input file into chunks...

REM Use a simpler approach to split the file
set /a CURRENT_LINE=0
set /a CHUNK_INDEX=0

REM Create temporary files for each chunk
if exist "%TEMP%\line_counter.txt" del "%TEMP%\line_counter.txt"
echo 0 > "%TEMP%\line_counter.txt"

echo Creating chunk files...
for /f "usebackq delims=" %%a in ("%INPUT_FILE%") do (
    REM Read current line counter
    set /p CURRENT_LINE=<"%TEMP%\line_counter.txt"
    
    REM Calculate which chunk this line belongs to
    set /a CHUNK_INDEX=CURRENT_LINE / LINES_PER_SERVER
    
    REM Append line to appropriate chunk file
    echo %%a >> "%OUTPUT_DIR%\chunk_%CHUNK_INDEX%.txt"
    
    REM Increment line counter
    set /a CURRENT_LINE+=1
    echo !CURRENT_LINE! > "%TEMP%\line_counter.txt"
    
    REM Show progress every 1000 lines
    set /a MOD=CURRENT_LINE %% 1000
    if !MOD! EQU 0 (
        echo Processed !CURRENT_LINE! of %TOTAL_LINES% lines
    )
)

echo All chunks created successfully

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
    if defined SERVER_ARRAY[%%i] (
        set SERVER=!SERVER_ARRAY[%%i]!
        set CHUNK_FILE=!CHUNK_FILES[%%i]!
        
        if defined CHUNK_FILE (
            set CHUNK=%OUTPUT_DIR%\!CHUNK_FILE!
            set OUTPUT_PREFIX=%OUTPUT_DIR%\result_!CHUNK_FILE!
            
            echo Starting client for server !SERVER! with chunk !CHUNK!
            
            REM Create a simplified command file for this specific job
            set "CMD_FILE=%TEMP%\run_client_%%i.cmd"
            echo @echo off > "!CMD_FILE!"
            echo cd /d "%CD%" >> "!CMD_FILE!"
            echo python client\email_validator_client.py "!CHUNK!" "!OUTPUT_PREFIX!" --servers "!SERVER!" --max-workers %WORKERS_PER_SERVER% --batch-size %BATCH_SIZE% --retry-limit 3 --timeout 30 >> "!CMD_FILE!"
            
            REM Run the command file in background
            start /b cmd /c "!CMD_FILE!" > "%OUTPUT_DIR%\log_!CHUNK_FILE!.log" 2>&1
            
            REM Store the process ID using a more reliable method
            for /f "tokens=2" %%p in ('tasklist /fi "imagename eq cmd.exe" /nh ^| findstr "cmd" ^| findstr /v "findstr"') do (
                echo %%p > "%OUTPUT_DIR%\pid_!CHUNK_FILE!.pid"
                goto :done_%%i
            )
            :done_%%i
            
            REM Sleep to avoid all clients starting at exactly the same time
            timeout /t 2 /nobreak > nul
        ) else (
            echo No chunk file found for server !SERVER!
        )
    ) else (
        echo No server defined for index %%i
    )
)

echo All clients started. Monitor progress with:
echo type %OUTPUT_DIR%\log_*.log
echo.
echo To stop all clients:
echo stop_distributed.bat %OUTPUT_DIR%

endlocal