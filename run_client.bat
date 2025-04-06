@echo off
REM Simple wrapper script to run a single email validation client
REM Usage: run_client.bat chunk_file output_prefix server max_workers batch_size

set CHUNK_FILE=%1
set OUTPUT_PREFIX=%2
set SERVER=%3
set MAX_WORKERS=%4
set BATCH_SIZE=%5

python client\email_validator_client.py "%CHUNK_FILE%" "%OUTPUT_PREFIX%" --servers %SERVER% --max-workers %MAX_WORKERS% --batch-size %BATCH_SIZE% --retry-limit 3 --timeout 30 