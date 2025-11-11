#!/bin/bash
set -e

# Push Docker image to AWS ECR
# Usage: ./scripts/push-ecr.sh [tag]

# Load environment variables
if [ -f .env.local ]; then
  export $(cat .env.local | grep -v '^#' | xargs)
fi

IMAGE_NAME="note-agent"
TAG="${1:-latest}"
ENVIRONMENT="${2:-dev}"

# Check required variables
if [ -z "$AWS_REGION" ]; then
  echo "❌ Error: AWS_REGION not set"
  exit 1
fi

if [ -z "$AWS_ACCOUNT_ID" ]; then
  echo "❌ Error: AWS_ACCOUNT_ID not set"
  exit 1
fi

ECR_REPOSITORY="${IMAGE_NAME}-${ENVIRONMENT}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_IMAGE="${ECR_REGISTRY}/${ECR_REPOSITORY}"

echo "Pushing to ECR: ${ECR_IMAGE}:${TAG}"

# Login to ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Tag the image
echo "Tagging image..."
docker tag "${IMAGE_NAME}:${TAG}" "${ECR_IMAGE}:${TAG}"
docker tag "${IMAGE_NAME}:${TAG}" "${ECR_IMAGE}:latest"

# Push the image
echo "Pushing image to ECR..."
docker push "${ECR_IMAGE}:${TAG}"
docker push "${ECR_IMAGE}:latest"

echo "✅ Successfully pushed to ECR"
echo "   Image: ${ECR_IMAGE}:${TAG}"
echo "   Also tagged as: ${ECR_IMAGE}:latest"
echo ""
echo "To deploy to ECS:"
echo "  ./scripts/deploy-ecs.sh"

