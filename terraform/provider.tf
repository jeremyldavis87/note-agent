terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: Uncomment to use S3 backend for state storage
  # backend "s3" {
  #   bucket         = "note-agent-terraform-state"
  #   key            = "note-agent/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "note-agent"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

