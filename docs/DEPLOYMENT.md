# Deployment Guide

This guide covers deploying the Note Agent service as a containerized microservice on AWS ECS.

## Architecture Overview

- **Container**: Docker container running FastAPI application
- **Compute**: AWS ECS Fargate (serverless containers)
- **Load Balancer**: Application Load Balancer (ALB)
- **Storage**: S3 for uploaded images
- **Registry**: ECR for Docker images
- **Infrastructure**: Managed with Terraform
- **CI/CD**: GitHub Actions for automated deployment

## Prerequisites

### Required Tools

1. **Docker** (for local building and testing)
   ```bash
   docker --version
   ```

2. **AWS CLI** (configured with credentials)
   ```bash
   aws --version
   aws configure
   ```

3. **Terraform** (version >= 1.0)
   ```bash
   terraform version
   ```

4. **jq** (for JSON processing in scripts)
   ```bash
   jq --version
   ```

### AWS Account Requirements

- AWS account with appropriate permissions
- IAM user with programmatic access
- Access keys configured in AWS CLI

### Required Permissions

Your AWS IAM user/role needs permissions for:
- ECS (cluster, service, task definition)
- EC2 (VPC, subnets, security groups, load balancer)
- ECR (repository access)
- S3 (bucket operations)
- IAM (role creation)
- CloudWatch (logs and metrics)

## Environment Variables

### Required Variables

Create a `.env` file based on `.env.local` with the following variables:

```bash
# AI/ML API Keys (REQUIRED)
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# AWS Configuration (REQUIRED)
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_S3_BUCKET=note-agent-uploads-dev

# API Configuration
API_CACHE_SIZE=100
API_CACHE_TTL=3600

# Application Settings
TEXT_AI_MODEL=gpt-4o-mini
AGENT_VISION_MODEL=gpt-4o-mini
LOG_LEVEL=INFO
DEBUG=false
```

## Local Development

### Build and Test Locally

1. **Build Docker image**:
   ```bash
   ./scripts/build-image.sh
   ```

2. **Run locally**:
   ```bash
   docker run -p 8000:8000 --env-file .env.local note-agent:latest
   ```

3. **Test the API**:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

4. **Access API documentation**:
   - Swagger UI: http://localhost:8000/api/v1/docs
   - ReDoc: http://localhost:8000/api/v1/redoc

## Infrastructure Deployment

### Step 1: Configure Terraform Variables

1. Navigate to terraform directory:
   ```bash
   cd terraform
   ```

2. Copy and customize terraform.tfvars:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

3. Edit `terraform.tfvars` with your values:
   ```hcl
   aws_region = "us-east-1"
   environment = "dev"
   
   openai_api_key = "your-openai-key"
   anthropic_api_key = "your-anthropic-key"
   ```

### Step 2: Initialize Terraform

```bash
terraform init
```

### Step 3: Plan Infrastructure

```bash
terraform plan
```

Review the plan to ensure all resources are correct.

### Step 4: Apply Infrastructure

```bash
terraform apply
```

This will create:
- VPC with public/private subnets
- Application Load Balancer
- ECS cluster and service
- S3 bucket for uploads
- ECR repository
- IAM roles and policies
- CloudWatch log groups and alarms

**Note**: Initial apply takes 10-15 minutes.

### Step 5: Get Outputs

```bash
terraform output
```

Save the following outputs:
- `alb_dns_name`: Load balancer URL
- `ecr_repository_url`: Docker registry URL
- `s3_bucket_name`: S3 bucket name

## Application Deployment

### Method 1: Using Scripts (Recommended)

1. **Build image**:
   ```bash
   ./scripts/build-image.sh $(git rev-parse --short HEAD)
   ```

2. **Push to ECR**:
   ```bash
   ./scripts/push-ecr.sh $(git rev-parse --short HEAD)
   ```

3. **Deploy to ECS**:
   ```bash
   ./scripts/deploy-ecs.sh
   ```

4. **Test deployment**:
   ```bash
   ./scripts/test-api.sh
   ```

### Method 2: Manual Deployment

1. **Login to ECR**:
   ```bash
   aws ecr get-login-password --region us-east-1 | \
     docker login --username AWS --password-stdin \
     123456789012.dkr.ecr.us-east-1.amazonaws.com
   ```

2. **Tag and push image**:
   ```bash
   docker tag note-agent:latest \
     123456789012.dkr.ecr.us-east-1.amazonaws.com/note-agent-dev:latest
   
   docker push \
     123456789012.dkr.ecr.us-east-1.amazonaws.com/note-agent-dev:latest
   ```

3. **Update ECS service**:
   ```bash
   aws ecs update-service \
     --cluster note-agent-cluster-dev \
     --service note-agent-service-dev \
     --force-new-deployment
   ```

## GitHub Actions CI/CD

### Setup GitHub Secrets

Add the following secrets to your GitHub repository:

1. Go to Settings → Secrets and variables → Actions
2. Add these secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_ACCOUNT_ID`
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `BRAINTRUST_API_KEY` (optional)

### Automated Deployment

The deployment workflow runs automatically on:
- Push to `main` branch
- Push to `feat/*` branches

Manual trigger:
1. Go to Actions → Build and Deploy to ECS
2. Click "Run workflow"

### Terraform from GitHub Actions

Infrastructure changes via GitHub Actions:

1. Go to Actions → Terraform Infrastructure
2. Click "Run workflow"
3. Select action: `plan`, `apply`, or `destroy`

## API Endpoints

Once deployed, the following endpoints are available:

### Core Endpoints

- `GET /api/v1/health` - Health check
- `POST /api/v1/upload` - Upload single image
- `POST /api/v1/upload/batch` - Upload multiple images
- `GET /api/v1/jobs` - List cached jobs
- `GET /api/v1/result/{job_id}` - Get job result
- `DELETE /api/v1/job/{job_id}` - Delete job

### Documentation

- `GET /api/v1/docs` - Swagger UI
- `GET /api/v1/redoc` - ReDoc documentation

## Example API Usage

### Upload Single Image

```bash
curl -X POST "http://<alb-dns>/api/v1/upload" \
  -F "file=@image.jpg" \
  -F "force_single=false"
```

Response:
```json
{
  "job_id": "abc123",
  "status": "completed",
  "result": { ... },
  "processing_time_seconds": 15.3,
  "s3_key": "uploads/abc123/image.jpg"
}
```

### Upload Multiple Images

```bash
curl -X POST "http://<alb-dns>/api/v1/upload/batch" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg"
```

### Get Result

```bash
curl "http://<alb-dns>/api/v1/result/abc123"
```

## Monitoring

### CloudWatch Logs

View application logs:
```bash
aws logs tail /ecs/note-agent-dev --follow
```

### CloudWatch Alarms

Alarms are configured for:
- High CPU utilization (> 80%)
- High memory utilization (> 80%)
- High response time (> 2s)
- Unhealthy hosts

### ECS Service Status

```bash
aws ecs describe-services \
  --cluster note-agent-cluster-dev \
  --services note-agent-service-dev
```

## Scaling

### Manual Scaling

Update desired task count:
```bash
aws ecs update-service \
  --cluster note-agent-cluster-dev \
  --service note-agent-service-dev \
  --desired-count 3
```

### Auto Scaling

Auto-scaling is configured based on:
- CPU utilization (target: 70%)
- Memory utilization (target: 75%)
- Request count per target (target: 1000)

Scaling limits:
- Min: 1 task
- Max: 5 tasks

## Troubleshooting

### Container Fails to Start

1. **Check CloudWatch logs**:
   ```bash
   aws logs tail /ecs/note-agent-dev --follow
   ```

2. **Check task status**:
   ```bash
   aws ecs list-tasks --cluster note-agent-cluster-dev
   aws ecs describe-tasks --cluster note-agent-cluster-dev --tasks <task-id>
   ```

3. **Common issues**:
   - Missing environment variables
   - Invalid API keys
   - S3 bucket not accessible
   - Image not found in ECR

### Service Unhealthy

1. **Check target group health**:
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn <target-group-arn>
   ```

2. **Check health endpoint**:
   ```bash
   curl http://<alb-dns>/api/v1/health
   ```

3. **Verify security groups**:
   - ALB security group allows inbound 80/443
   - ECS task security group allows inbound from ALB

### High Response Times

1. **Increase task CPU/memory** (edit `terraform/variables.tf`):
   ```hcl
   ecs_task_cpu = 4096
   ecs_task_memory = 8192
   ```

2. **Increase parallel processing** (environment variable):
   ```
   AGENT_PARALLEL_PROCESSING_LIMIT=10
   ```

3. **Scale up tasks**:
   ```bash
   aws ecs update-service \
     --cluster note-agent-cluster-dev \
     --service note-agent-service-dev \
     --desired-count 5
   ```

## Cost Optimization

### Development Environment

For cost-effective development:
- Use 1 task minimum
- Use FARGATE_SPOT for non-critical workloads
- Set S3 lifecycle rules (already configured)
- Delete unused ECS task definitions

### Production Recommendations

- Use reserved capacity for predictable workloads
- Enable S3 Intelligent-Tiering
- Use CloudWatch Logs retention policies
- Implement API rate limiting

## Cleanup

### Destroy Infrastructure

**WARNING**: This will delete all resources!

```bash
cd terraform
terraform destroy
```

Or via GitHub Actions:
1. Actions → Terraform Infrastructure
2. Run workflow → Select "destroy"

### Manual Cleanup

If Terraform destroy fails:

1. **Empty S3 bucket**:
   ```bash
   aws s3 rm s3://note-agent-uploads-dev --recursive
   ```

2. **Delete ECR images**:
   ```bash
   aws ecr batch-delete-image \
     --repository-name note-agent-dev \
     --image-ids imageTag=latest
   ```

3. **Run terraform destroy again**:
   ```bash
   terraform destroy -auto-approve
   ```

## Security Best Practices

1. **API Keys**: Store in AWS Secrets Manager (not in task definition)
2. **S3 Bucket**: Enable versioning and encryption (already configured)
3. **ALB**: Add HTTPS listener with ACM certificate
4. **WAF**: Add AWS WAF for API protection
5. **VPC**: Use private subnets for ECS tasks (already configured)
6. **IAM**: Follow principle of least privilege (already configured)

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review GitHub Issues
3. Consult AWS ECS documentation

## Additional Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

