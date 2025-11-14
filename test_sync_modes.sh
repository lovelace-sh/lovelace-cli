#!/bin/bash
# Test script for sync vs watch (one-way vs two-way)

echo "=== Lovelace Sync Modes Test ==="
echo

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Create test directories
TEST_DIR="/tmp/lovelace-sync-test-$$"
mkdir -p "$TEST_DIR/one-way"
mkdir -p "$TEST_DIR/two-way"

echo "Test directories created:"
echo "  One-way: $TEST_DIR/one-way"
echo "  Two-way: $TEST_DIR/two-way"
echo

# Test 1: One-way sync (lovelace sync)
echo -e "${BLUE}Test 1: One-way sync (lovelace sync)${NC}"
cd "$TEST_DIR/one-way"

# Initialize (you'll need to provide credentials)
echo "Initializing one-way test directory..."
lovelace init

# Create a local file
echo "test content" > local_file.txt
echo "Created local_file.txt"

# Run sync (should NOT upload local changes)
echo "Running 'lovelace sync' (one-way: remote → local)..."
lovelace sync

echo "Check if local_file.txt was uploaded to remote (it shouldn't be)"
echo -e "${GREEN}Expected: Local file NOT synced to remote${NC}"
echo

# Test 2: Two-way sync (lovelace watch)
echo -e "${BLUE}Test 2: Two-way sync (lovelace watch)${NC}"
cd "$TEST_DIR/two-way"

# Initialize
echo "Initializing two-way test directory..."
lovelace init

# Create a local file
echo "test content" > local_file.txt
echo "Created local_file.txt"

# Run watch once (should upload local changes)
echo "Running 'lovelace watch --once' (two-way: local ↔ remote)..."
lovelace watch --once

echo "Check if local_file.txt was uploaded to remote (it should be)"
echo -e "${GREEN}Expected: Local file synced to remote${NC}"
echo

# Cleanup
echo "Cleaning up..."
cd /
rm -rf "$TEST_DIR"

echo
echo "=== Manual Verification Required ==="
echo "1. Check your remote storage after Test 1 - local_file.txt should NOT appear"
echo "2. Check your remote storage after Test 2 - local_file.txt SHOULD appear"
echo
echo "=== Test Complete ==="