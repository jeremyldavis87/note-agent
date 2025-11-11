# S3 Bucket for Image Uploads
resource "aws_s3_bucket" "uploads" {
  bucket = "${var.project_name}-uploads-${var.environment}"

  tags = {
    Name = "${var.project_name}-uploads-${var.environment}"
  }
}

# S3 Bucket Versioning
resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket Server-Side Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 Bucket Public Access Block
resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket Lifecycle Configuration
resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "delete-old-uploads"
    status = "Enabled"

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }

    filter {
      prefix = "uploads/"
    }
  }

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    transition {
      days          = 7
      storage_class = "STANDARD_IA"
    }

    filter {
      prefix = "uploads/"
    }
  }
}

# S3 Bucket CORS Configuration (if needed for direct uploads from browser)
resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = ["*"] # Restrict this in production
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

