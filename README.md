# Note Agent

A microservice that converts images containing handwritten notes into structured JSON using vision LLM and text enrichment. Available as both a local CLI tool and a containerized REST API.

## Setup

1. Create a virtual environment (Python 3.12):
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

       2. Install system dependencies (required for QR code and Data Matrix code detection):
       ```bash
       # On Ubuntu 24.04:
       sudo apt-get update
       sudo apt-get install -y libzbar0t64 libdmtx0t64

       # On older Ubuntu/Debian:
       sudo apt-get update
       sudo apt-get install -y libzbar0 libdmtx1

       # On macOS (using Homebrew):
       brew install zbar libdmtx
       ```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Copy `.env.local` to `.env` and adjust values as needed.

## Run

```bash
python -m src.cli --image test-notes-image.jpg --out out.json
```

Flags:
- `--single-note` to force single-note processing
- `--trace` to enable Braintrust tracing (if configured)

## Models and providers
- Vision and text models are selected via `.env` settings (`AGENT_VISION_MODEL`, `TEXT_AI_MODEL`).
- Providers are chosen by the factory based on model names and which API keys are present (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

## Compare to expected output
```bash
python scripts/compare_expected.py --actual out.json --expected expected-output.json
```

## Deployment Options

### Option 1: Local CLI (Development)

Run locally as a command-line tool. Output is written to a JSON file.

### Option 2: API Service (Production)

Deploy as a containerized microservice on AWS ECS with REST API endpoints.

**Quick Start:**
```bash
# Build Docker image
./scripts/build-image.sh

# Deploy to AWS ECS
cd terraform
terraform init
terraform apply
```

**API Endpoints:**
- `POST /api/v1/upload` - Upload and process single image
- `POST /api/v1/upload/batch` - Process multiple images
- `GET /api/v1/health` - Health check
- `GET /api/v1/docs` - API documentation

**Features:**
- Synchronous processing with JSON response
- S3 storage for uploaded images
- In-memory caching for recent results
- Auto-scaling based on load
- CloudWatch logging and monitoring

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for complete deployment guide.

## Architecture

- **API Framework**: FastAPI
- **Compute**: AWS ECS Fargate
- **Storage**: S3 for images
- **Registry**: ECR for Docker images
- **Infrastructure**: Terraform
- **CI/CD**: GitHub Actions

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md) - Complete deployment instructions
- [Features](docs/FEATURES.md) - Supported features and capabilities
- [Integration Guide](INTEGRATION_GUIDE.md) - How to integrate with other services

## Notes
- Local CLI: No database required, output written to JSON files
- API Service: Results returned in API response, cached in memory
