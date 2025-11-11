#!/bin/bash
set -e

# Deploy to ECS by forcing a new deployment
# Usage: ./scripts/deploy-ecs.sh [environment]

# Load environment variables
if [ -f .env.local ]; then
  export $(cat .env.local | grep -v '^#' | xargs)
fi

ENVIRONMENT="${1:-dev}"
PROJECT_NAME="note-agent"
ECS_CLUSTER="${PROJECT_NAME}-cluster-${ENVIRONMENT}"
ECS_SERVICE="${PROJECT_NAME}-service-${ENVIRONMENT}"

# Check required variables
if [ -z "$AWS_REGION" ]; then
  echo "❌ Error: AWS_REGION not set"
  exit 1
fi

echo "Deploying to ECS..."
echo "  Cluster: ${ECS_CLUSTER}"
echo "  Service: ${ECS_SERVICE}"
echo "  Region: ${AWS_REGION}"

# Update ECS service to force new deployment
aws ecs update-service \
  --cluster "$ECS_CLUSTER" \
  --service "$ECS_SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION" \
  > /dev/null

echo "✅ Deployment initiated"
echo ""
echo "Waiting for service to stabilize..."

# Wait for the service to stabilize
aws ecs wait services-stable \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$AWS_REGION"

echo "✅ Service is stable"
echo ""

# Get service status
echo "Service Status:"
aws ecs describe-services \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" \
  --region "$AWS_REGION" \
  --query 'services[0].{Status:status,DesiredCount:desiredCount,RunningCount:runningCount,PendingCount:pendingCount}' \
  --output table

# Get ALB URL
echo ""
echo "Getting ALB URL..."
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --region "$AWS_REGION" \
  --query "LoadBalancers[?contains(LoadBalancerName, '${PROJECT_NAME}')].DNSName" \
  --output text 2>/dev/null || echo "")

if [ -n "$ALB_DNS" ]; then
  echo "✅ Application URL: http://${ALB_DNS}"
  echo "   Health check: http://${ALB_DNS}/api/v1/health"
  echo "   API docs: http://${ALB_DNS}/api/v1/docs"
else
  echo "⚠️  Could not determine ALB URL"
fi

