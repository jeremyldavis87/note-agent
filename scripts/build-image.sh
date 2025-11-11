#!/bin/bash
set -e

# Build Docker image locally
# Usage: ./scripts/build-image.sh [tag]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="note-agent"
TAG="${1:-latest}"

echo "Building Docker image: ${IMAGE_NAME}:${TAG}"
echo "Project directory: ${PROJECT_DIR}"

cd "$PROJECT_DIR"

# Build the image
docker build \
  --tag "${IMAGE_NAME}:${TAG}" \
  --file Dockerfile \
  .

echo "✅ Successfully built ${IMAGE_NAME}:${TAG}"

# Show image info
docker images "${IMAGE_NAME}:${TAG}"

echo ""
echo "To run the image locally:"
echo "  docker run -p 8000:8000 --env-file .env.local ${IMAGE_NAME}:${TAG}"
echo ""
echo "To push to ECR:"
echo "  ./scripts/push-ecr.sh ${TAG}"

