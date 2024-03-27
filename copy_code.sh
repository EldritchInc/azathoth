#!/bin/bash

# Directories to exclude
EXCLUDE_DIRS="node_modules .vscode build __pycache__ dist venv .git .idea .pytest_cache __snapshots__ coverage .nyc_output .next .cache public out tmp temp logs .tmp .temp .logs .bak .swp .swo"

# Define file patterns to include
INCLUDE_PATTERNS="*.js *.html *.css *.config *.py *.sh *.md *.txt"

# Start with the base find command
FIND_CMD="find ./azathoth ./tests -type f"

# Append exclusion rules for each directory
for EXCLUDE_DIR in $EXCLUDE_DIRS; do
  FIND_CMD="$FIND_CMD -not -path '*/$EXCLUDE_DIR/*'"
done

# Append inclusion patterns using a subshell to group conditions correctly
FIND_CMD="$FIND_CMD \( "
first=1
for INCLUDE_PATTERN in $INCLUDE_PATTERNS; do
  if [ $first -eq 1 ]; then
    first=0
    FIND_CMD="$FIND_CMD -name '$INCLUDE_PATTERN'"
  else
    FIND_CMD="$FIND_CMD -o -name '$INCLUDE_PATTERN'"
  fi
done
FIND_CMD="$FIND_CMD \)"

# Use eval to execute the find command, filter results, and copy to clipboard
eval "$FIND_CMD" | xargs cat | pbcopy

echo "Content copied to clipboard."
