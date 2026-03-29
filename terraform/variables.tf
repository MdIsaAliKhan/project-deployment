# ============================================================
# terraform/variables.tf
# EKS + RDS — all configurable variables
# ============================================================

# ── AWS & Cluster ─────────────────────────────────────────
variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster (used as prefix for all resources)"
  type        = string
  default     = "lms-eks-cluster"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# ── EKS Node Group ────────────────────────────────────────
variable "node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "t3.medium"
}

variable "desired_nodes" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 2
}

variable "min_nodes" {
  description = "Minimum number of EKS worker nodes"
  type        = number
  default     = 1
}

variable "max_nodes" {
  description = "Maximum number of EKS worker nodes"
  type        = number
  default     = 5
}

# ── RDS (MySQL) ───────────────────────────────────────────
variable "db_name" {
  description = "Name of the MySQL database"
  type        = string
  default     = "online_exam"
}

variable "db_username" {
  description = "Master username for the RDS instance"
  type        = string
  default     = "lmsadmin"
  # Never put the real value here — pass via terraform.tfvars or env var
}

variable "db_password" {
  description = "Master password for the RDS instance"
  type        = string
  sensitive   = true
  # Set via: export TF_VAR_db_password="yourpassword"
  # Or in terraform.tfvars (never commit to Git)
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"   # cheapest — upgrade to db.t3.small for production
}

variable "db_allocated_storage" {
  description = "Initial storage in GB for RDS"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum storage in GB for RDS auto-scaling"
  type        = number
  default     = 100
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automated RDS backups (0 = disabled)"
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Prevent accidental RDS deletion (set false only to destroy)"
  type        = bool
  default     = true
}

variable "db_multi_az" {
  description = "Enable Multi-AZ for RDS high availability"
  type        = bool
  default     = false   # set true for production HA
}
