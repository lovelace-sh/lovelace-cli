import os
import hashlib
import logging
import click
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

class SyncError(Exception):
    pass

class R2Sync:
    def __init__(self, config: Dict[str, str], show_progress: bool = True):
        self.bucket_name = config.get("bucket")
        # Keep the prefix as-is from config (with trailing slash if present)
        self.prefix = config.get("prefix", "")
        self.endpoint_url = config.get("endpoint_url")
        self.show_progress = show_progress
        
        try:
            # Configure S3 client with R2 temporary credentials
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=config.get("access_key_id"),
                aws_secret_access_key=config.get("secret_access_key"),
                aws_session_token=config.get("session_token"),
                region_name=config.get("region", "auto"),
                config=Config(signature_version='s3v4')
            )
        except Exception as e:
            raise SyncError(f"Failed to initialize S3 client: {e}")
        
        self.local_root = Path.cwd()
    
    def _get_file_hash(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def _get_remote_files(self) -> Dict[str, Dict]:
        remote_files = {}
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=self.prefix
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if self.prefix:
                            relative_key = key[len(self.prefix):].lstrip('/')
                        else:
                            relative_key = key
                        
                        if relative_key:
                            remote_files[relative_key] = {
                                'key': key,
                                'size': obj['Size'],
                                'last_modified': obj['LastModified'],
                                'etag': obj.get('ETag', '').strip('"')
                            }
            
            return remote_files
        except ClientError as e:
            raise SyncError(f"Failed to list remote files: {e}")
    
    def _get_local_files(self) -> Dict[str, Dict]:
        local_files = {}

        for root, dirs, files in os.walk(self.local_root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                # Skip the .lovelace config file
                if file == '.lovelace':
                    continue

                file_path = Path(root) / file
                relative_path = file_path.relative_to(self.local_root)
                
                try:
                    stat = file_path.stat()
                    local_files[str(relative_path)] = {
                        'path': file_path,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime),
                        'hash': self._get_file_hash(file_path)
                    }
                except Exception as e:
                    logger.warning(f"Failed to stat local file {file_path}: {e}")
        
        return local_files
    
    def _download_file(self, remote_key: str, local_path: Path) -> bool:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)

            temp_path = local_path.with_suffix('.tmp')
            self.s3_client.download_file(
                self.bucket_name,
                remote_key,
                str(temp_path)
            )

            temp_path.replace(local_path)
            if self.show_progress and local_path.name != '.gitkeep':
                click.echo(f"  ✓ {local_path.relative_to(self.local_root)}")
            return True

        except ClientError as e:
            logger.error(f"Failed to download {remote_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {remote_key}: {e}")
            return False

    def _upload_file(self, local_path: Path, remote_key: str) -> bool:
        """Upload a local file to R2 storage"""
        try:
            if not local_path.exists():
                logger.debug(f"Local file does not exist: {local_path}")
                return False

            self.s3_client.upload_file(
                str(local_path),
                self.bucket_name,
                remote_key
            )

            if self.show_progress and local_path.name != '.gitkeep':
                click.echo(f"  ✓ Uploaded {local_path.relative_to(self.local_root)}")
            return True

        except ClientError as e:
            logger.error(f"Failed to upload {remote_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {remote_key}: {e}")
            return False

    def _delete_remote_file(self, remote_key: str) -> bool:
        """Delete a file from R2 storage"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=remote_key
            )

            if self.show_progress:
                # Extract relative path from remote key
                if self.prefix:
                    relative_path = remote_key[len(self.prefix):].lstrip('/')
                else:
                    relative_path = remote_key
                click.echo(f"  ✓ Deleted from remote: {relative_path}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete {remote_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting {remote_key}: {e}")
            return False
    
    def _should_update_file(self, local_info: Dict, remote_info: Dict) -> bool:
        # If hashes match, files are identical - no need to update
        if local_info['hash'] == remote_info['etag']:
            return False

        # Hashes differ, so we need to update
        return True
    
    def sync(self, dry_run: bool = False) -> Tuple[List[str], List[str], List[str]]:
        
        remote_files = self._get_remote_files()
        local_files = self._get_local_files()
        
        files_to_download = []
        files_to_update = []
        files_to_delete = []
        
        for remote_path, remote_info in remote_files.items():
            local_path = self.local_root / remote_path
            
            if remote_path not in local_files:
                files_to_download.append((remote_path, local_path, remote_info['key']))
            else:
                local_info = local_files[remote_path]
                if self._should_update_file(local_info, remote_info):
                    files_to_update.append((remote_path, local_path, remote_info['key']))
        
        for local_path in local_files:
            if local_path not in remote_files:
                files_to_delete.append(local_files[local_path]['path'])
        
        if dry_run:
            return (
                [f[0] for f in files_to_download],
                [f[0] for f in files_to_update],
                [str(f) for f in files_to_delete]
            )
        
        downloaded = []
        for remote_path, local_path, remote_key in files_to_download:
            if self._download_file(remote_key, local_path):
                # Don't count .gitkeep files in the results
                if local_path.name != '.gitkeep':
                    downloaded.append(remote_path)

        updated = []
        for remote_path, local_path, remote_key in files_to_update:
            if self._download_file(remote_key, local_path):
                # Don't count .gitkeep files in the results
                if local_path.name != '.gitkeep':
                    updated.append(remote_path)

        deleted = []
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                if self.show_progress and file_path.name != '.gitkeep':
                    click.echo(f"  ✓ Deleted {file_path.relative_to(self.local_root)}")
                # Don't count .gitkeep files in the results
                if file_path.name != '.gitkeep':
                    deleted.append(str(file_path))

                parent = file_path.parent
                while parent != self.local_root:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                    except:
                        break
                    parent = parent.parent

            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        return downloaded, updated, deleted