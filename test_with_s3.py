#!/usr/bin/env python3
"""
Test Lovelace sync with LocalStack S3
Requires: pip install localstack awscli-local
"""

import os
import subprocess
import time
import tempfile
import shutil

def setup_localstack():
    """Start LocalStack with S3"""
    print("Starting LocalStack...")
    proc = subprocess.Popen(
        ["localstack", "start", "-d"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(10)  # Wait for startup
    
    # Create test bucket and files
    print("Creating test bucket...")
    subprocess.run(["awslocal", "s3", "mb", "s3://test-bucket"])
    
    # Upload test files
    test_dir = tempfile.mkdtemp()
    os.makedirs(f"{test_dir}/projects/project1", exist_ok=True)
    
    # Create test files
    with open(f"{test_dir}/projects/project1/file1.txt", "w") as f:
        f.write("Test file 1")
    with open(f"{test_dir}/projects/project1/file2.txt", "w") as f:
        f.write("Test file 2")
    
    # Upload to LocalStack
    subprocess.run([
        "awslocal", "s3", "sync", 
        f"{test_dir}/projects/project1",
        "s3://test-bucket/projects/project1"
    ])
    
    print("Test files uploaded to LocalStack S3")
    shutil.rmtree(test_dir)
    
    return proc

def test_sync():
    """Test the sync functionality"""
    # Create test directory
    test_dir = tempfile.mkdtemp()
    os.chdir(test_dir)
    
    # Create mock .lovelace config
    config = {
        "project_id": "proj-1",
        "project_name": "Test Project",
        "bucket": "test-bucket",
        "prefix": "projects/project1",
        "endpoint_url": "http://localhost:4566",
        "access_key_id": "test",
        "secret_access_key": "test",
        "token": "test-token"
    }
    
    import json
    with open(".lovelace", "w") as f:
        json.dump(config, f)
    
    print(f"Test directory: {test_dir}")
    
    # Run sync
    print("\nRunning 'lovelace sync --dry-run'...")
    subprocess.run(["lovelace", "sync", "--dry-run"])
    
    print("\nRunning 'lovelace sync'...")
    result = subprocess.run(["lovelace", "sync"], capture_output=True, text=True)
    print(result.stdout)
    
    # Check files were synced
    if os.path.exists("file1.txt") and os.path.exists("file2.txt"):
        print("✓ Files successfully synced!")
    else:
        print("✗ Sync failed")
    
    # Cleanup
    os.chdir("/")
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    # Note: Requires LocalStack to be installed
    # pip install localstack awscli-local
    
    try:
        proc = setup_localstack()
        test_sync()
    finally:
        print("\nStopping LocalStack...")
        subprocess.run(["localstack", "stop"])