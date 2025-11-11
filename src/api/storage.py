"""S3 storage wrapper for image uploads and downloads."""

import io
import logging
from pathlib import Path
from typing import BinaryIO, Optional
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from .exceptions import StorageError

logger = logging.getLogger(__name__)


class S3Storage:
    """S3 storage client for managing image uploads and downloads."""
    
    def __init__(
        self,
        bucket_name: str,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ):
        """
        Initialize S3 storage client.
        
        Args:
            bucket_name: S3 bucket name
            region_name: AWS region
            aws_access_key_id: AWS access key (optional, uses IAM role if not provided)
            aws_secret_access_key: AWS secret key (optional, uses IAM role if not provided)
        """
        self.bucket_name = bucket_name
        self.region_name = region_name
        
        # Create S3 client with credentials if provided, otherwise use IAM role
        session_kwargs = {"region_name": region_name}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs.update({
                "aws_access_key_id": aws_access_key_id,
                "aws_secret_access_key": aws_secret_access_key
            })
        
        self.s3_client = boto3.client("s3", **session_kwargs)
        logger.info(f"Initialized S3 storage client for bucket: {bucket_name}")
    
    def upload_file(
        self,
        file_data: BinaryIO,
        object_key: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload file to S3.
        
        Args:
            file_data: File-like object containing the data
            object_key: S3 object key (path within bucket)
            content_type: MIME type of the file
            
        Returns:
            S3 object key
            
        Raises:
            StorageError: If upload fails
        """
        try:
            self.s3_client.upload_fileobj(
                file_data,
                self.bucket_name,
                object_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ServerSideEncryption": "AES256"
                }
            )
            logger.info(f"Uploaded file to S3: {object_key}")
            return object_key
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Failed to upload file to S3: {str(e)}"
            logger.error(error_msg)
            raise StorageError(error_msg, details={"object_key": object_key})
    
    def download_file(self, object_key: str) -> bytes:
        """
        Download file from S3.
        
        Args:
            object_key: S3 object key
            
        Returns:
            File contents as bytes
            
        Raises:
            StorageError: If download fails
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            data = response["Body"].read()
            logger.info(f"Downloaded file from S3: {object_key}")
            return data
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Failed to download file from S3: {str(e)}"
            logger.error(error_msg)
            raise StorageError(error_msg, details={"object_key": object_key})
    
    def delete_file(self, object_key: str) -> None:
        """
        Delete file from S3.
        
        Args:
            object_key: S3 object key
            
        Raises:
            StorageError: If deletion fails
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            logger.info(f"Deleted file from S3: {object_key}")
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Failed to delete file from S3: {str(e)}"
            logger.error(error_msg)
            raise StorageError(error_msg, details={"object_key": object_key})
    
    def file_exists(self, object_key: str) -> bool:
        """
        Check if file exists in S3.
        
        Args:
            object_key: S3 object key
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            # Re-raise other errors
            logger.error(f"Error checking file existence: {str(e)}")
            raise StorageError(
                f"Failed to check file existence: {str(e)}",
                details={"object_key": object_key}
            )
    
    def generate_presigned_url(
        self,
        object_key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate a presigned URL for downloading a file.
        
        Args:
            object_key: S3 object key
            expiration: URL expiration time in seconds
            
        Returns:
            Presigned URL
            
        Raises:
            StorageError: If URL generation fails
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_key
                },
                ExpiresIn=expiration
            )
            logger.info(f"Generated presigned URL for: {object_key}")
            return url
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Failed to generate presigned URL: {str(e)}"
            logger.error(error_msg)
            raise StorageError(error_msg, details={"object_key": object_key})
    
    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[str]:
        """
        List files in S3 bucket with optional prefix.
        
        Args:
            prefix: Prefix to filter objects
            max_keys: Maximum number of keys to return
            
        Returns:
            List of object keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            if "Contents" not in response:
                return []
            
            keys = [obj["Key"] for obj in response["Contents"]]
            logger.info(f"Listed {len(keys)} files with prefix: {prefix}")
            return keys
        except (ClientError, BotoCoreError) as e:
            error_msg = f"Failed to list files: {str(e)}"
            logger.error(error_msg)
            raise StorageError(error_msg, details={"prefix": prefix})

