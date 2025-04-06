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

REM Helper function to count lines in a file
if exist "%TEMP%\count_lines.bat" del "%TEMP%\count_lines.bat"
echo @echo off > "%TEMP%\count_lines.bat"
echo for /f %%%%A in ('type "%%~1" ^| find /c /v ""') do set count=%%%%A >> "%TEMP%\count_lines.bat"
echo exit /b 0 >> "%TEMP%\count_lines.bat"

REM Create empty result files
type nul > "%MERGED_PREFIX%_valid.txt"
type nul > "%MERGED_PREFIX%_invalid.txt"
type nul > "%MERGED_PREFIX%_disposable.txt"
type nul > "%MERGED_PREFIX%_unknown.txt"

REM Merge valid emails
echo Merging valid emails...
for %%f in ("%OUTPUT_DIR%\result_*_valid.txt") do (
    if exist "%%f" (
        type "%%f" >> "%MERGED_PREFIX%_valid.txt"
    )
)

REM Sort and remove duplicates
echo Sorting valid emails and removing duplicates...
if exist "%MERGED_PREFIX%_valid.txt.tmp" del "%MERGED_PREFIX%_valid.txt.tmp"
sort "%MERGED_PREFIX%_valid.txt" /o "%MERGED_PREFIX%_valid.txt.tmp"
findstr /v /r "^$" "%MERGED_PREFIX%_valid.txt.tmp" > "%MERGED_PREFIX%_valid.txt"
call "%TEMP%\count_lines.bat" "%MERGED_PREFIX%_valid.txt"
set VALID_COUNT=%count%

REM Merge invalid emails
echo Merging invalid emails...
for %%f in ("%OUTPUT_DIR%\result_*_invalid.txt") do (
    if exist "%%f" (
        type "%%f" >> "%MERGED_PREFIX%_invalid.txt"
    )
)

REM Sort and remove duplicates
echo Sorting invalid emails and removing duplicates...
if exist "%MERGED_PREFIX%_invalid.txt.tmp" del "%MERGED_PREFIX%_invalid.txt.tmp"
sort "%MERGED_PREFIX%_invalid.txt" /o "%MERGED_PREFIX%_invalid.txt.tmp"
findstr /v /r "^$" "%MERGED_PREFIX%_invalid.txt.tmp" > "%MERGED_PREFIX%_invalid.txt"
call "%TEMP%\count_lines.bat" "%MERGED_PREFIX%_invalid.txt"
set INVALID_COUNT=%count%

REM Merge disposable emails
echo Merging disposable emails...
for %%f in ("%OUTPUT_DIR%\result_*_disposable.txt") do (
    if exist "%%f" (
        type "%%f" >> "%MERGED_PREFIX%_disposable.txt"
    )
)

REM Sort and remove duplicates
echo Sorting disposable emails and removing duplicates...
if exist "%MERGED_PREFIX%_disposable.txt.tmp" del "%MERGED_PREFIX%_disposable.txt.tmp"
sort "%MERGED_PREFIX%_disposable.txt" /o "%MERGED_PREFIX%_disposable.txt.tmp"
findstr /v /r "^$" "%MERGED_PREFIX%_disposable.txt.tmp" > "%MERGED_PREFIX%_disposable.txt"
call "%TEMP%\count_lines.bat" "%MERGED_PREFIX%_disposable.txt"
set DISPOSABLE_COUNT=%count%

REM Merge unknown emails
echo Merging unknown emails...
for %%f in ("%OUTPUT_DIR%\result_*_unknown.txt") do (
    if exist "%%f" (
        type "%%f" >> "%MERGED_PREFIX%_unknown.txt"
    )
)

REM Sort and remove duplicates
echo Sorting unknown emails and removing duplicates...
if exist "%MERGED_PREFIX%_unknown.txt.tmp" del "%MERGED_PREFIX%_unknown.txt.tmp"
sort "%MERGED_PREFIX%_unknown.txt" /o "%MERGED_PREFIX%_unknown.txt.tmp"
findstr /v /r "^$" "%MERGED_PREFIX%_unknown.txt.tmp" > "%MERGED_PREFIX%_unknown.txt"
call "%TEMP%\count_lines.bat" "%MERGED_PREFIX%_unknown.txt"
set UNKNOWN_COUNT=%count%

REM Clean up temp files
del "%MERGED_PREFIX%_*.txt.tmp" 2>nul
del "%TEMP%\count_lines.bat" 2>nul

REM Calculate total
set /a TOTAL_COUNT=%VALID_COUNT% + %INVALID_COUNT% + %DISPOSABLE_COUNT% + %UNKNOWN_COUNT%

echo.
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