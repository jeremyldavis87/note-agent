#!/bin/bash
set -e

# Test the deployed API
# Usage: ./scripts/test-api.sh [alb-url]

ALB_URL="${1}"

if [ -z "$ALB_URL" ]; then
  # Try to get ALB URL from AWS
  if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
  fi
  
  if [ -n "$AWS_REGION" ]; then
    ALB_DNS=$(aws elbv2 describe-load-balancers \
      --region "$AWS_REGION" \
      --query "LoadBalancers[?contains(LoadBalancerName, 'note-agent')].DNSName" \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$ALB_DNS" ]; then
      ALB_URL="http://${ALB_DNS}"
    fi
  fi
fi

if [ -z "$ALB_URL" ]; then
  echo "Usage: $0 <alb-url>"
  echo "Example: $0 http://note-agent-alb-dev-123456789.us-east-1.elb.amazonaws.com"
  exit 1
fi

echo "Testing API at: ${ALB_URL}"
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${ALB_URL}/api/v1/health")
HTTP_CODE=$(echo "$HEALTH_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Health check passed"
  echo "$HEALTH_RESPONSE" | grep -v "HTTP_CODE:"
else
  echo "❌ Health check failed (HTTP $HTTP_CODE)"
  exit 1
fi

echo ""

# Test upload endpoint (requires an image file)
TEST_IMAGE="test/test-notes-image.jpg"
if [ -f "$TEST_IMAGE" ]; then
  echo "2. Testing upload endpoint..."
  UPLOAD_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -X POST "${ALB_URL}/api/v1/upload" \
    -F "file=@${TEST_IMAGE}")
  
  HTTP_CODE=$(echo "$UPLOAD_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Upload test passed"
    JOB_ID=$(echo "$UPLOAD_RESPONSE" | grep -v "HTTP_CODE:" | jq -r '.job_id')
    echo "   Job ID: $JOB_ID"
  else
    echo "❌ Upload test failed (HTTP $HTTP_CODE)"
    echo "$UPLOAD_RESPONSE" | grep -v "HTTP_CODE:"
  fi
  
  echo ""
  
  # Test result endpoint
  if [ -n "$JOB_ID" ]; then
    echo "3. Testing result endpoint..."
    RESULT_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
      "${ALB_URL}/api/v1/result/${JOB_ID}")
    
    HTTP_CODE=$(echo "$RESULT_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
    
    if [ "$HTTP_CODE" = "200" ]; then
      echo "✅ Result retrieval passed"
    else
      echo "❌ Result retrieval failed (HTTP $HTTP_CODE)"
    fi
    
    echo ""
  fi
else
  echo "⚠️  Test image not found: $TEST_IMAGE"
  echo "   Skipping upload test"
fi

# Test jobs endpoint
echo "4. Testing jobs list endpoint..."
JOBS_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  "${ALB_URL}/api/v1/jobs")

HTTP_CODE=$(echo "$JOBS_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Jobs list passed"
  TOTAL_JOBS=$(echo "$JOBS_RESPONSE" | grep -v "HTTP_CODE:" | jq -r '.total')
  echo "   Total jobs: $TOTAL_JOBS"
else
  echo "❌ Jobs list failed (HTTP $HTTP_CODE)"
fi

echo ""
echo "API Documentation: ${ALB_URL}/api/v1/docs"
echo "✅ API tests completed"

