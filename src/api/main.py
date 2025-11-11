"""FastAPI application for note extraction service."""

import io
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ..config import settings
from ..pipeline import process_image, process_multiple_images
from .models import (
    HealthResponse,
    UploadResponse,
    BatchUploadResponse,
    JobListResponse,
    JobInfo,
    ResultResponse,
    DeleteResponse,
    ErrorResponse,
)
from .cache import LRUCache
from .storage import S3Storage
from .exceptions import APIException, ImageProcessingError, StorageError, NotFoundError

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Note Extraction API",
    description="Extract structured data from images of handwritten notes",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize cache
cache = LRUCache(
    max_size=getattr(settings, "API_CACHE_SIZE", 100),
    ttl_seconds=getattr(settings, "API_CACHE_TTL", 3600)
)

# Initialize S3 storage (if configured)
s3_storage: Optional[S3Storage] = None
if hasattr(settings, "AWS_S3_BUCKET") and settings.AWS_S3_BUCKET:
    try:
        s3_storage = S3Storage(
            bucket_name=settings.AWS_S3_BUCKET,
            region_name=getattr(settings, "AWS_REGION", "us-east-1"),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
        )
        logger.info("S3 storage initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize S3 storage: {e}. File uploads will not be stored.")
        s3_storage = None
else:
    logger.warning("AWS_S3_BUCKET not configured. File uploads will not be stored.")


@app.exception_handler(APIException)
async def api_exception_handler(request, exc: APIException):
    """Handle custom API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.__class__.__name__,
            message=exc.message,
            details=exc.details,
            timestamp=datetime.utcnow()
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="InternalServerError",
            message="An unexpected error occurred",
            details={"error": str(exc)},
            timestamp=datetime.utcnow()
        ).model_dump()
    )


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and version information.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow()
    )


@app.post("/api/v1/upload", response_model=UploadResponse, tags=["Processing"])
async def upload_image(
    file: UploadFile = File(..., description="Image file to process"),
    force_single: bool = False
):
    """
    Upload and process a single image.
    
    Args:
        file: Image file (JPEG, PNG)
        force_single: Force single-note processing mode
        
    Returns:
        Processing results with job ID
    """
    job_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(f"Job {job_id}: Starting single image upload")
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (JPEG, PNG, etc.)"
        )
    
    # Read file data
    try:
        file_data = await file.read()
        if len(file_data) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum of {settings.MAX_FILE_SIZE} bytes"
            )
    except Exception as e:
        logger.error(f"Job {job_id}: Failed to read file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    
    # Upload to S3 if configured
    s3_key = None
    if s3_storage:
        try:
            s3_key = f"uploads/{job_id}/{file.filename}"
            s3_storage.upload_file(
                io.BytesIO(file_data),
                s3_key,
                content_type=file.content_type
            )
            logger.info(f"Job {job_id}: Uploaded to S3: {s3_key}")
        except StorageError as e:
            logger.warning(f"Job {job_id}: S3 upload failed: {e.message}")
            # Continue processing even if S3 upload fails
    
    # Save to temporary file for processing
    temp_dir = Path("/tmp/note-agent")
    temp_dir.mkdir(exist_ok=True)
    temp_file = temp_dir / f"{job_id}_{file.filename}"
    
    try:
        temp_file.write_bytes(file_data)
        logger.info(f"Job {job_id}: Saved to temp file: {temp_file}")
        
        # Process image
        logger.info(f"Job {job_id}: Starting image processing")
        doc = process_image(temp_file, force_single=force_single)
        
        processing_time = time.time() - start_time
        logger.info(f"Job {job_id}: Processing completed in {processing_time:.2f}s")
        
        # Cache result
        cache_data = {
            "job_id": job_id,
            "status": "completed",
            "result": doc.model_dump(),
            "created_at": datetime.utcnow(),
            "processing_time_seconds": processing_time,
            "image_count": 1,
            "s3_key": s3_key
        }
        cache.set(job_id, cache_data)
        
        return UploadResponse(
            job_id=job_id,
            status="completed",
            result=doc,
            processing_time_seconds=processing_time,
            s3_key=s3_key,
            message="Image processed successfully"
        )
        
    except Exception as e:
        logger.error(f"Job {job_id}: Processing failed: {e}", exc_info=True)
        processing_time = time.time() - start_time
        
        # Cache error result
        cache_data = {
            "job_id": job_id,
            "status": "failed",
            "result": None,
            "created_at": datetime.utcnow(),
            "processing_time_seconds": processing_time,
            "image_count": 1,
            "error": str(e)
        }
        cache.set(job_id, cache_data)
        
        raise ImageProcessingError(
            f"Failed to process image: {str(e)}",
            details={"job_id": job_id}
        )
    finally:
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()
            logger.debug(f"Job {job_id}: Cleaned up temp file")


@app.post("/api/v1/upload/batch", response_model=BatchUploadResponse, tags=["Processing"])
async def upload_batch(
    files: List[UploadFile] = File(..., description="Multiple image files to process"),
    force_single: bool = False
):
    """
    Upload and process multiple images in batch.
    
    Args:
        files: List of image files
        force_single: Force single-note processing mode for each image
        
    Returns:
        Aggregated processing results with job ID
    """
    job_id = str(uuid.uuid4())
    start_time = time.time()
    
    logger.info(f"Job {job_id}: Starting batch upload with {len(files)} images")
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed per batch")
    
    temp_dir = Path("/tmp/note-agent")
    temp_dir.mkdir(exist_ok=True)
    temp_files = []
    s3_keys = []
    
    try:
        # Process each file
        for idx, file in enumerate(files):
            # Validate file type
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=f"File {idx + 1} must be an image"
                )
            
            # Read file data
            file_data = await file.read()
            if len(file_data) > settings.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File {idx + 1} exceeds maximum size"
                )
            
            # Upload to S3 if configured
            if s3_storage:
                try:
                    s3_key = f"uploads/{job_id}/{idx}_{file.filename}"
                    s3_storage.upload_file(
                        io.BytesIO(file_data),
                        s3_key,
                        content_type=file.content_type
                    )
                    s3_keys.append(s3_key)
                    logger.info(f"Job {job_id}: Uploaded file {idx + 1} to S3: {s3_key}")
                except StorageError as e:
                    logger.warning(f"Job {job_id}: S3 upload failed for file {idx + 1}: {e.message}")
            
            # Save to temp file
            temp_file = temp_dir / f"{job_id}_{idx}_{file.filename}"
            temp_file.write_bytes(file_data)
            temp_files.append(str(temp_file))
            logger.debug(f"Job {job_id}: Saved file {idx + 1} to temp: {temp_file}")
        
        # Process images with aggregation
        logger.info(f"Job {job_id}: Starting batch processing")
        output_file = temp_dir / f"{job_id}_output.json"
        process_multiple_images(temp_files, str(output_file), force_single=force_single)
        
        # Read aggregated result
        import json
        result = json.loads(output_file.read_text())
        
        processing_time = time.time() - start_time
        logger.info(f"Job {job_id}: Batch processing completed in {processing_time:.2f}s")
        
        # Cache result
        cache_data = {
            "job_id": job_id,
            "status": "completed",
            "result": result,
            "created_at": datetime.utcnow(),
            "processing_time_seconds": processing_time,
            "image_count": len(files),
            "s3_keys": s3_keys
        }
        cache.set(job_id, cache_data)
        
        # Clean up output file
        if output_file.exists():
            output_file.unlink()
        
        return BatchUploadResponse(
            job_id=job_id,
            status="completed",
            result=result,
            processing_time_seconds=processing_time,
            images_processed=len(files),
            s3_keys=s3_keys,
            message="Batch processing completed successfully"
        )
        
    except Exception as e:
        logger.error(f"Job {job_id}: Batch processing failed: {e}", exc_info=True)
        processing_time = time.time() - start_time
        
        # Cache error result
        cache_data = {
            "job_id": job_id,
            "status": "failed",
            "result": None,
            "created_at": datetime.utcnow(),
            "processing_time_seconds": processing_time,
            "image_count": len(files),
            "error": str(e)
        }
        cache.set(job_id, cache_data)
        
        raise ImageProcessingError(
            f"Failed to process batch: {str(e)}",
            details={"job_id": job_id}
        )
    finally:
        # Clean up temp files
        for temp_file in temp_files:
            temp_path = Path(temp_file)
            if temp_path.exists():
                temp_path.unlink()
        logger.debug(f"Job {job_id}: Cleaned up {len(temp_files)} temp files")


@app.get("/api/v1/jobs", response_model=JobListResponse, tags=["Jobs"])
async def list_jobs():
    """
    List all cached jobs.
    
    Returns:
        List of job information
    """
    job_keys = cache.list_keys()
    jobs = []
    
    for job_id in job_keys:
        job_data = cache.get(job_id)
        if job_data:
            jobs.append(JobInfo(
                job_id=job_data["job_id"],
                status=job_data["status"],
                created_at=job_data["created_at"],
                processing_time_seconds=job_data.get("processing_time_seconds"),
                image_count=job_data.get("image_count", 1)
            ))
    
    # Sort by created_at descending
    jobs.sort(key=lambda x: x.created_at, reverse=True)
    
    return JobListResponse(jobs=jobs, total=len(jobs))


@app.get("/api/v1/result/{job_id}", response_model=ResultResponse, tags=["Jobs"])
async def get_result(job_id: str):
    """
    Get processing result for a specific job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Job result if found
    """
    job_data = cache.get(job_id)
    
    if not job_data:
        raise NotFoundError(
            f"Job not found: {job_id}",
            details={"job_id": job_id}
        )
    
    return ResultResponse(
        job_id=job_data["job_id"],
        status=job_data["status"],
        result=job_data.get("result"),
        created_at=job_data["created_at"],
        processing_time_seconds=job_data.get("processing_time_seconds")
    )


@app.delete("/api/v1/job/{job_id}", response_model=DeleteResponse, tags=["Jobs"])
async def delete_job(job_id: str):
    """
    Delete a cached job result.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Deletion status
    """
    deleted = cache.delete(job_id)
    
    if not deleted:
        raise NotFoundError(
            f"Job not found: {job_id}",
            details={"job_id": job_id}
        )
    
    # Also delete from S3 if exists
    if s3_storage:
        try:
            # Try to delete the uploads directory for this job
            prefix = f"uploads/{job_id}/"
            files = s3_storage.list_files(prefix=prefix)
            for s3_key in files:
                s3_storage.delete_file(s3_key)
            logger.info(f"Deleted {len(files)} files from S3 for job {job_id}")
        except Exception as e:
            logger.warning(f"Failed to delete S3 files for job {job_id}: {e}")
    
    return DeleteResponse(
        job_id=job_id,
        deleted=True,
        message=f"Job {job_id} deleted successfully"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

