#!/bin/bash

# Merge results from distributed email validation
# Usage: ./merge_results.sh output_dir merged_output_prefix

if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <output_dir> <merged_output_prefix>"
    exit 1
fi

OUTPUT_DIR=$1
MERGED_PREFIX=$2

# Check if output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory $OUTPUT_DIR does not exist."
    exit 1
fi

# Create output directory for merged results if needed
MERGED_DIR=$(dirname "$MERGED_PREFIX")
mkdir -p "$MERGED_DIR"

# Merge valid emails
echo "Merging valid emails..."
cat "$OUTPUT_DIR"/result_*_valid.txt > "${MERGED_PREFIX}_valid.txt"
# Sort and remove duplicates
sort -u "${MERGED_PREFIX}_valid.txt" -o "${MERGED_PREFIX}_valid.txt"
VALID_COUNT=$(wc -l < "${MERGED_PREFIX}_valid.txt")

# Merge invalid emails
echo "Merging invalid emails..."
cat "$OUTPUT_DIR"/result_*_invalid.txt > "${MERGED_PREFIX}_invalid.txt"
# Sort and remove duplicates
sort -u "${MERGED_PREFIX}_invalid.txt" -o "${MERGED_PREFIX}_invalid.txt"
INVALID_COUNT=$(wc -l < "${MERGED_PREFIX}_invalid.txt")

# Merge disposable emails
echo "Merging disposable emails..."
if ls "$OUTPUT_DIR"/result_*_disposable.txt 1> /dev/null 2>&1; then
    cat "$OUTPUT_DIR"/result_*_disposable.txt > "${MERGED_PREFIX}_disposable.txt"
    # Sort and remove duplicates
    sort -u "${MERGED_PREFIX}_disposable.txt" -o "${MERGED_PREFIX}_disposable.txt"
    DISPOSABLE_COUNT=$(wc -l < "${MERGED_PREFIX}_disposable.txt")
else
    echo "No disposable email files found"
    DISPOSABLE_COUNT=0
fi

# Merge unknown emails
echo "Merging unknown emails..."
cat "$OUTPUT_DIR"/result_*_unknown.txt > "${MERGED_PREFIX}_unknown.txt"
# Sort and remove duplicates
sort -u "${MERGED_PREFIX}_unknown.txt" -o "${MERGED_PREFIX}_unknown.txt"
UNKNOWN_COUNT=$(wc -l < "${MERGED_PREFIX}_unknown.txt")

# Calculate total
TOTAL_COUNT=$((VALID_COUNT + INVALID_COUNT + DISPOSABLE_COUNT + UNKNOWN_COUNT))

echo "Results merged successfully:"
echo "- Valid emails: $VALID_COUNT"
echo "- Invalid emails: $INVALID_COUNT"
echo "- Disposable emails: $DISPOSABLE_COUNT"
echo "- Unknown emails: $UNKNOWN_COUNT"
echo "- Total: $TOTAL_COUNT"
echo ""
echo "Output files:"
echo "- ${MERGED_PREFIX}_valid.txt"
echo "- ${MERGED_PREFIX}_invalid.txt"
echo "- ${MERGED_PREFIX}_disposable.txt"
echo "- ${MERGED_PREFIX}_unknown.txt" 