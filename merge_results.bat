@echo off
setlocal enabledelayedexpansion

REM Merge results from distributed email validation
REM Usage: merge_results.bat output_dir merged_output_prefix

if "%~2"=="" (
    echo Usage: %0 ^<output_dir^> ^<merged_output_prefix^>
    exit /b 1
)

set OUTPUT_DIR=%~1
set MERGED_PREFIX=%~2

REM Check if output directory exists
if not exist "%OUTPUT_DIR%" (
    echo Error: Output directory %OUTPUT_DIR% does not exist.
    exit /b 1
)

REM Create output directory for merged results if needed
for %%i in ("%MERGED_PREFIX%") do set MERGED_DIR=%%~dpi
if not exist "%MERGED_DIR%" mkdir "%MERGED_DIR%"

REM Merge valid emails
echo Merging valid emails...
type "%OUTPUT_DIR%\result_*_valid.txt" > "%MERGED_PREFIX%_valid.txt" 2>nul
REM Sort and remove duplicates using PowerShell
powershell -Command "Get-Content '%MERGED_PREFIX%_valid.txt' | Sort-Object -Unique | Set-Content '%MERGED_PREFIX%_valid.txt'"
for /f %%a in ('type "%MERGED_PREFIX%_valid.txt" ^| find /c /v ""') do set VALID_COUNT=%%a

REM Merge invalid emails
echo Merging invalid emails...
type "%OUTPUT_DIR%\result_*_invalid.txt" > "%MERGED_PREFIX%_invalid.txt" 2>nul
REM Sort and remove duplicates
powershell -Command "Get-Content '%MERGED_PREFIX%_invalid.txt' | Sort-Object -Unique | Set-Content '%MERGED_PREFIX%_invalid.txt'"
for /f %%a in ('type "%MERGED_PREFIX%_invalid.txt" ^| find /c /v ""') do set INVALID_COUNT=%%a

REM Merge disposable emails
echo Merging disposable emails...
set DISPOSABLE_COUNT=0
if exist "%OUTPUT_DIR%\result_*_disposable.txt" (
    type "%OUTPUT_DIR%\result_*_disposable.txt" > "%MERGED_PREFIX%_disposable.txt" 2>nul
    REM Sort and remove duplicates
    powershell -Command "Get-Content '%MERGED_PREFIX%_disposable.txt' | Sort-Object -Unique | Set-Content '%MERGED_PREFIX%_disposable.txt'"
    for /f %%a in ('type "%MERGED_PREFIX%_disposable.txt" ^| find /c /v ""') do set DISPOSABLE_COUNT=%%a
) else (
    echo No disposable email files found
    echo. > "%MERGED_PREFIX%_disposable.txt"
)

REM Merge unknown emails
echo Merging unknown emails...
type "%OUTPUT_DIR%\result_*_unknown.txt" > "%MERGED_PREFIX%_unknown.txt" 2>nul
REM Sort and remove duplicates
powershell -Command "Get-Content '%MERGED_PREFIX%_unknown.txt' | Sort-Object -Unique | Set-Content '%MERGED_PREFIX%_unknown.txt'"
for /f %%a in ('type "%MERGED_PREFIX%_unknown.txt" ^| find /c /v ""') do set UNKNOWN_COUNT=%%a

REM Calculate total
set /a TOTAL_COUNT=%VALID_COUNT% + %INVALID_COUNT% + %DISPOSABLE_COUNT% + %UNKNOWN_COUNT%

echo Results merged successfully:
echo - Valid emails: %VALID_COUNT%
echo - Invalid emails: %INVALID_COUNT%
echo - Disposable emails: %DISPOSABLE_COUNT%
echo - Unknown emails: %UNKNOWN_COUNT%
echo - Total: %TOTAL_COUNT%
echo.
echo Output files:
echo - %MERGED_PREFIX%_valid.txt
echo - %MERGED_PREFIX%_invalid.txt
echo - %MERGED_PREFIX%_disposable.txt
echo - %MERGED_PREFIX%_unknown.txt

endlocal