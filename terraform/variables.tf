variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "note-agent"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to use"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

# ECS Configuration
variable "ecs_task_cpu" {
  description = "CPU units for ECS task (1024 = 1 vCPU)"
  type        = number
  default     = 2048
}

variable "ecs_task_memory" {
  description = "Memory for ECS task in MB"
  type        = number
  default     = 4096
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 5
}

# Application Configuration
variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 8000
}

variable "health_check_path" {
  description = "Health check path"
  type        = string
  default     = "/api/v1/health"
}

# Environment Variables for ECS
variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "braintrust_api_key" {
  description = "Braintrust API key (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "text_ai_model" {
  description = "Text AI model to use"
  type        = string
  default     = "gpt-4o-mini"
}

variable "agent_vision_model" {
  description = "Vision AI model to use"
  type        = string
  default     = "gpt-4o-mini"
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "debug" {
  description = "Enable debug mode"
  type        = bool
  default     = false
}

