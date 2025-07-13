"""
Cloudflare R2 Storage Manager for Video Generation Platform
"""
import os
import boto3
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError, NoCredentialsError
import asyncio
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)

class R2StorageManager:
    """Manages video storage on Cloudflare R2 with 7-day access management"""
    
    def __init__(self):
        self.account_id = os.environ.get('R2_ACCOUNT_ID')
        self.access_key = os.environ.get('R2_ACCESS_KEY')
        self.secret_key = os.environ.get('R2_SECRET_KEY')
        self.bucket_name = os.environ.get('R2_BUCKET_NAME')
        self.endpoint = os.environ.get('R2_ENDPOINT')
        
        if not all([self.account_id, self.access_key, self.secret_key, self.bucket_name]):
            raise ValueError("Missing required R2 credentials in environment variables")
        
        # Initialize boto3 client for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name='auto'
        )
        
        logger.info(f"R2StorageManager initialized for bucket: {self.bucket_name}")
    
    def generate_video_key(self, video_id: str, generation_id: str, file_extension: str = "mp4") -> str:
        """Generate a unique storage key for a video"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"generated/{video_id}/{generation_id}_{timestamp}.{file_extension}"
    
    def generate_upload_key(self, user_id: str, filename: str) -> str:
        """Generate a unique storage key for uploaded videos"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        return f"uploads/{user_id}/{timestamp}_{safe_filename}"
    
    async def upload_file(self, file_path: str, storage_key: str, metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload a file to R2 storage"""
        try:
            # Prepare metadata
            upload_metadata = {
                'upload_timestamp': datetime.utcnow().isoformat(),
                'expires_at': (datetime.utcnow() + timedelta(days=7)).isoformat()
            }
            if metadata:
                upload_metadata.update(metadata)
            
            # Upload file
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.upload_file(
                    file_path,
                    self.bucket_name,
                    storage_key,
                    ExtraArgs={'Metadata': upload_metadata}
                )
            )
            
            file_size = os.path.getsize(file_path)
            
            logger.info(f"Successfully uploaded {file_path} to R2 as {storage_key}")
            
            return {
                'success': True,
                'storage_key': storage_key,
                'bucket': self.bucket_name,
                'file_size': file_size,
                'metadata': upload_metadata,
                'upload_time': datetime.utcnow().isoformat()
            }
            
        except FileNotFoundError:
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        except ClientError as e:
            error_msg = f"R2 upload error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        except Exception as e:
            error_msg = f"Unexpected upload error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def upload_from_bytes(self, file_data: bytes, storage_key: str, metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload file data directly from bytes to R2"""
        try:
            # Prepare metadata
            upload_metadata = {
                'upload_timestamp': datetime.utcnow().isoformat(),
                'expires_at': (datetime.utcnow() + timedelta(days=7)).isoformat()
            }
            if metadata:
                upload_metadata.update(metadata)
            
            # Upload bytes
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=storage_key,
                    Body=file_data,
                    Metadata=upload_metadata
                )
            )
            
            logger.info(f"Successfully uploaded {len(file_data)} bytes to R2 as {storage_key}")
            
            return {
                'success': True,
                'storage_key': storage_key,
                'bucket': self.bucket_name,
                'file_size': len(file_data),
                'metadata': upload_metadata,
                'upload_time': datetime.utcnow().isoformat()
            }
            
        except ClientError as e:
            error_msg = f"R2 upload error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        except Exception as e:
            error_msg = f"Unexpected upload error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def generate_presigned_url(self, storage_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for downloading a file"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': storage_key},
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned URL for {storage_key}")
            return url
        
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None
    
    def generate_presigned_upload_url(self, storage_key: str, expiration: int = 3600) -> Optional[str]:
        """Generate a presigned URL for uploading a file"""
        try:
            url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': self.bucket_name, 'Key': storage_key},
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned upload URL for {storage_key}")
            return url
        
        except ClientError as e:
            logger.error(f"Error generating presigned upload URL: {str(e)}")
            return None
    
    async def download_file(self, storage_key: str, local_path: str) -> Dict[str, Any]:
        """Download a file from R2 to local storage"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.download_file(
                    self.bucket_name,
                    storage_key,
                    local_path
                )
            )
            
            file_size = os.path.getsize(local_path)
            logger.info(f"Successfully downloaded {storage_key} to {local_path}")
            
            return {
                'success': True,
                'local_path': local_path,
                'storage_key': storage_key,
                'file_size': file_size
            }
            
        except ClientError as e:
            error_msg = f"R2 download error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        
        except Exception as e:
            error_msg = f"Unexpected download error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    async def delete_file(self, storage_key: str) -> Dict[str, Any]:
        """Delete a file from R2 storage"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=storage_key
                )
            )
            
            logger.info(f"Successfully deleted {storage_key} from R2")
            return {'success': True, 'deleted_key': storage_key}
            
        except ClientError as e:
            error_msg = f"R2 delete error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def list_expired_files(self) -> List[Dict[str, Any]]:
        """List files that have exceeded their 7-day expiration"""
        try:
            expired_files = []
            current_time = datetime.utcnow()
            
            # List all objects in bucket
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        # Check if file is older than 7 days
                        file_age = current_time - obj['LastModified'].replace(tzinfo=None)
                        if file_age.days >= 7:
                            expired_files.append({
                                'key': obj['Key'],
                                'last_modified': obj['LastModified'].isoformat(),
                                'size': obj['Size'],
                                'age_days': file_age.days
                            })
            
            logger.info(f"Found {len(expired_files)} expired files")
            return expired_files
            
        except ClientError as e:
            logger.error(f"Error listing expired files: {str(e)}")
            return []
    
    async def cleanup_expired_files(self) -> Dict[str, Any]:
        """Delete files that have exceeded their 7-day expiration"""
        try:
            expired_files = self.list_expired_files()
            deleted_count = 0
            failed_deletions = []
            
            for file_info in expired_files:
                delete_result = await self.delete_file(file_info['key'])
                if delete_result['success']:
                    deleted_count += 1
                else:
                    failed_deletions.append({
                        'key': file_info['key'],
                        'error': delete_result['error']
                    })
            
            logger.info(f"Cleanup completed: {deleted_count} files deleted, {len(failed_deletions)} failed")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'failed_count': len(failed_deletions),
                'failed_deletions': failed_deletions
            }
            
        except Exception as e:
            error_msg = f"Cleanup error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_file_info(self, storage_key: str) -> Optional[Dict[str, Any]]:
        """Get metadata and information about a file in R2"""
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            
            return {
                'key': storage_key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat(),
                'metadata': response.get('Metadata', {}),
                'content_type': response.get('ContentType', 'unknown')
            }
            
        except ClientError as e:
            logger.error(f"Error getting file info for {storage_key}: {str(e)}")
            return None

# Global storage manager instance
storage_manager = R2StorageManager()