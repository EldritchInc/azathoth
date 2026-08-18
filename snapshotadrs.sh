#!/usr/bin/env bash

set -euo pipefail

OUTPUT="adr_snapshot.txt"
ADR_DIR="docs/adrs"

if [[ ! -d "$ADR_DIR" ]]; then
    echo "ADR directory not found: $ADR_DIR" >&2
    exit 1
fi

: > "$OUTPUT"

{
    echo "AZATHOTH ADR SNAPSHOT"
    echo "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "Commit: $(git rev-parse HEAD)"
    echo "Branch: $(git branch --show-current)"
    echo
} >> "$OUTPUT"

while IFS= read -r file; do
    {
        echo
        echo "================================================================================"
        echo "FILE: $file"
        echo "================================================================================"
        echo
        cat "$file"
        echo
    } >> "$OUTPUT"
done < <(
    find "$ADR_DIR" -type f -name '*.md' -print | sort
)

echo "Generated $OUTPUT"
echo "$(find "$ADR_DIR" -type f -name '*.md' | wc -l | tr -d ' ') ADRs included."
