#!/bin/bash
# Test script for Lovelace CLI with mock server

echo "=== Lovelace CLI Test Suite ==="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Start mock server in background
echo "Starting mock API server..."
python test_server.py &
SERVER_PID=$!
sleep 2

# Create test directory
TEST_DIR="/tmp/lovelace-test-$$"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "Test directory: $TEST_DIR"
echo

# Override API URL for testing
export LOVELACE_API_URL="http://localhost:5000/api/cli/auth"

# Test 1: Check version
echo "Test 1: Version check"
if lovelace --version; then
    echo -e "${GREEN}✓ Version check passed${NC}"
else
    echo -e "${RED}✗ Version check failed${NC}"
fi
echo

# Test 2: Init in non-empty directory (should fail)
echo "Test 2: Init in non-empty directory"
echo "test" > testfile.txt
if ! lovelace init 2>/dev/null; then
    echo -e "${GREEN}✓ Correctly rejected non-empty directory${NC}"
else
    echo -e "${RED}✗ Should have rejected non-empty directory${NC}"
fi
rm testfile.txt
echo

# Test 3: Init with mock credentials
echo "Test 3: Initialize with mock credentials"
echo -e "testuser\ntestpass\n1\n" | lovelace init
if [ -f ".lovelace" ]; then
    echo -e "${GREEN}✓ Configuration file created${NC}"
else
    echo -e "${RED}✗ Configuration file not created${NC}"
fi
echo

# Test 4: Status command
echo "Test 4: Status check"
if lovelace status; then
    echo -e "${GREEN}✓ Status command successful${NC}"
else
    echo -e "${RED}✗ Status command failed${NC}"
fi
echo

# Test 5: Unlink command
echo "Test 5: Unlink configuration"
lovelace unlink
if [ ! -f ".lovelace" ]; then
    echo -e "${GREEN}✓ Configuration file removed${NC}"
else
    echo -e "${RED}✗ Configuration file still exists${NC}"
fi
echo

# Cleanup
echo "Cleaning up..."
kill $SERVER_PID 2>/dev/null
cd /
rm -rf "$TEST_DIR"

echo
echo "=== Test Suite Complete ==="