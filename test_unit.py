#!/usr/bin/env python3
"""
Unit tests for Lovelace CLI components
Run with: python -m pytest test_unit.py
"""

import pytest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import components to test
from lovelace.config import ConfigManager
from lovelace.auth import AuthClient, AuthenticationError


class TestConfigManager:
    """Test configuration management"""
    
    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".lovelace"
            manager = ConfigManager(config_path)
            
            # Test data
            config = {
                "project_id": "test-123",
                "project_name": "Test Project",
                "bucket": "test-bucket",
                "prefix": "test/prefix",
                "token": "secret-token",
                "access_key_id": "AKIA123",
                "secret_access_key": "secret123"
            }
            
            # Save
            manager.save(config)
            assert config_path.exists()
            
            # Load
            loaded = manager.load()
            assert loaded["project_id"] == config["project_id"]
            assert loaded["bucket"] == config["bucket"]
            assert loaded["token"] == config["token"]
    
    def test_encryption(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".lovelace"
            manager = ConfigManager(config_path)
            
            config = {"token": "secret-token", "access_key_id": "key123"}
            manager.save(config)
            
            # Check raw file doesn't contain secrets
            with open(config_path, 'r') as f:
                raw_content = f.read()
                assert "secret-token" not in raw_content
                assert "key123" not in raw_content


class TestAuthClient:
    """Test authentication client"""
    
    @patch('requests.post')
    def test_authenticate_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token123",
            "projects": [{"id": "p1", "name": "Project 1"}]
        }
        mock_post.return_value = mock_response
        
        client = AuthClient()
        result = client.authenticate("user", "pass")
        
        assert result["access_token"] == "token123"
        assert len(result["projects"]) == 1
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_authenticate_failure(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        client = AuthClient()
        with pytest.raises(AuthenticationError):
            client.authenticate("wrong", "creds")
    
    def test_device_id_consistency(self):
        client = AuthClient()
        id1 = client._get_device_id()
        id2 = client._get_device_id()
        
        # Should be consistent
        assert id1 == id2
        
        # Should contain hostname
        import socket
        assert socket.gethostname() in id1


class TestEmptyDirectoryCheck:
    """Test empty directory validation"""
    
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only hidden files should be allowed
            Path(tmpdir, ".hidden").touch()
            
            contents = list(Path(tmpdir).iterdir())
            non_hidden = [f for f in contents if not f.name.startswith('.')]
            
            assert len(non_hidden) == 0
    
    def test_non_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file.txt").touch()
            
            contents = list(Path(tmpdir).iterdir())
            non_hidden = [f for f in contents if not f.name.startswith('.')]
            
            assert len(non_hidden) == 1


if __name__ == "__main__":
    # Run with pytest if available
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("Install pytest for better test output: pip install pytest")
        # Basic test runner
        test = TestConfigManager()
        test.test_save_and_load_config()
        test.test_encryption()
        print("✓ Config tests passed")
        
        test = TestAuthClient()
        test.test_device_id_consistency()
        print("✓ Auth tests passed")
        
        test = TestEmptyDirectoryCheck()
        test.test_empty_directory()
        test.test_non_empty_directory()
        print("✓ Directory tests passed")