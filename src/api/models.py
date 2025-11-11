"""Pydantic models for API requests and responses."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ..schema import Document, ImageMetadata, Note, Summary


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Current server time")


class UploadResponse(BaseModel):
    """Response for single image upload."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Processing status")
    result: Optional[Document] = Field(None, description="Extraction results")
    processing_time_seconds: Optional[float] = Field(None, description="Processing time")
    s3_key: Optional[str] = Field(None, description="S3 object key for uploaded image")
    message: Optional[str] = Field(None, description="Status message or error details")


class BatchUploadResponse(BaseModel):
    """Response for batch image upload."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Processing status")
    result: Optional[dict] = Field(None, description="Aggregated extraction results")
    processing_time_seconds: Optional[float] = Field(None, description="Processing time")
    images_processed: int = Field(..., description="Number of images processed")
    s3_keys: List[str] = Field(default_factory=list, description="S3 object keys for uploaded images")
    message: Optional[str] = Field(None, description="Status message or error details")


class JobInfo(BaseModel):
    """Information about a processing job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status (completed, failed, etc.)")
    created_at: datetime = Field(..., description="Job creation timestamp")
    processing_time_seconds: Optional[float] = Field(None, description="Processing time")
    image_count: int = Field(..., description="Number of images in job")


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: List[JobInfo] = Field(..., description="List of job information")
    total: int = Field(..., description="Total number of jobs in cache")


class ResultResponse(BaseModel):
    """Response for retrieving job results."""
    job_id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="Job status")
    result: Optional[dict] = Field(None, description="Processing results")
    created_at: datetime = Field(..., description="Job creation timestamp")
    processing_time_seconds: Optional[float] = Field(None, description="Processing time")


class DeleteResponse(BaseModel):
    """Response for deleting a job."""
    job_id: str = Field(..., description="Job identifier")
    deleted: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Deletion status message")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(..., description="Error timestamp")

