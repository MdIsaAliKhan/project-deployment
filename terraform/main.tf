# ============================================================
# terraform/main.tf
# University LMS — EKS + RDS (MySQL) Production Setup
# ============================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # ── Remote State (recommended — uncomment after creating the S3 bucket) ───
  # backend "s3" {
  #   bucket         = "lms-terraform-state-YOURACCOUNTID"
  #   key            = "lms/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "lms-terraform-locks"   # for state locking
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "university-lms"
      ManagedBy   = "terraform"
      Environment = "production"
    }
  }
}

# ── Data Sources ──────────────────────────────────────────────────────────────
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# ─────────────────────────────────────────────────────────────────────────────
# VPC
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_vpc" "lms_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true   # required for RDS endpoint resolution
  enable_dns_support   = true

  tags = {
    Name                                        = "${var.cluster_name}-vpc"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

# ── Public Subnets (ALB / Load Balancer tier) ─────────────────────────────────
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.lms_vpc.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                        = "${var.cluster_name}-public-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

# ── Private Subnets (EKS worker nodes) ───────────────────────────────────────
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.lms_vpc.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name                                        = "${var.cluster_name}-private-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
}

# ── RDS Subnets (isolated — separate from EKS nodes) ─────────────────────────
# RDS gets its own dedicated subnets in different AZs for Multi-AZ support.
# These are NOT routed to the internet at all.
resource "aws_subnet" "rds" {
  count             = 2
  vpc_id            = aws_vpc.lms_vpc.id
  cidr_block        = "10.0.${count.index + 20}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.cluster_name}-rds-${count.index}"
    Tier = "database"
  }
}

# ── Internet Gateway ──────────────────────────────────────────────────────────
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.lms_vpc.id
  tags   = { Name = "${var.cluster_name}-igw" }
}

# ── NAT Gateway (private subnets → internet for image pulls) ─────────────────
resource "aws_eip" "nat" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.igw]
  tags       = { Name = "${var.cluster_name}-nat-eip" }
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.cluster_name}-nat" }
  depends_on    = [aws_internet_gateway.igw]
}

# ── Route Tables ──────────────────────────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lms_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "${var.cluster_name}-public-rt" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.lms_vpc.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = { Name = "${var.cluster_name}-private-rt" }
}

# RDS subnets have NO route to internet — database isolation
resource "aws_route_table" "rds" {
  vpc_id = aws_vpc.lms_vpc.id
  tags   = { Name = "${var.cluster_name}-rds-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "rds" {
  count          = 2
  subnet_id      = aws_subnet.rds[count.index].id
  route_table_id = aws_route_table.rds.id
}

# ─────────────────────────────────────────────────────────────────────────────
# SECURITY GROUPS
# ─────────────────────────────────────────────────────────────────────────────

# ── EKS Node Security Group ───────────────────────────────────────────────────
resource "aws_security_group" "eks_nodes" {
  name        = "${var.cluster_name}-eks-nodes-sg"
  description = "Security group for EKS worker nodes"
  vpc_id      = aws_vpc.lms_vpc.id

  # Allow all outbound (pods need internet for ECR pulls, AWS APIs)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  # Allow inbound from within VPC (node-to-node, EKS control plane)
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
    description = "Allow all inbound within VPC"
  }

  tags = { Name = "${var.cluster_name}-eks-nodes-sg" }
}

# ── RDS Security Group ────────────────────────────────────────────────────────
# CRITICAL: Only allows MySQL (3306) from EKS nodes — nothing else
resource "aws_security_group" "rds" {
  name        = "${var.cluster_name}-rds-sg"
  description = "Allow MySQL access only from EKS worker nodes"
  vpc_id      = aws_vpc.lms_vpc.id

  # Allow MySQL ONLY from EKS node security group
  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_nodes.id]
    description     = "MySQL from EKS nodes only"
  }

  # No outbound rules needed for RDS (it only receives connections)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow outbound for RDS maintenance"
  }

  tags = { Name = "${var.cluster_name}-rds-sg" }
}

# ─────────────────────────────────────────────────────────────────────────────
# IAM ROLES — EKS
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_iam_role" "eks_cluster_role" {
  name = "${var.cluster_name}-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster_role.name
}

resource "aws_iam_role" "eks_node_role" {
  name = "${var.cluster_name}-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_node_role.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_node_role.name
}

resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_node_role.name
}

# Allow EKS nodes to read secrets from AWS Secrets Manager
resource "aws_iam_role_policy_attachment" "secrets_manager_read" {
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
  role       = aws_iam_role.eks_node_role.name
}

# ─────────────────────────────────────────────────────────────────────────────
# EKS CLUSTER
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_eks_cluster" "lms_cluster" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = "1.29"

  vpc_config {
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
    security_group_ids      = [aws_security_group.eks_nodes.id]
    endpoint_public_access  = true
    endpoint_private_access = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
  tags       = { Name = var.cluster_name }
}

# ── EKS Node Group ────────────────────────────────────────────────────────────
resource "aws_eks_node_group" "lms_nodes" {
  cluster_name    = aws_eks_cluster.lms_cluster.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = aws_iam_role.eks_node_role.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = [var.node_instance_type]

  scaling_config {
    desired_size = var.desired_nodes
    min_size     = var.min_nodes
    max_size     = var.max_nodes
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_read_only,
    aws_iam_role_policy_attachment.secrets_manager_read,
  ]

  tags = { Name = "${var.cluster_name}-nodes" }
}

# ─────────────────────────────────────────────────────────────────────────────
# RDS — MySQL (Production Grade)
# ─────────────────────────────────────────────────────────────────────────────

# DB Subnet Group — RDS must span ≥2 AZs even if not Multi-AZ
resource "aws_db_subnet_group" "lms_rds" {
  name        = "${var.cluster_name}-rds-subnet-group"
  subnet_ids  = aws_subnet.rds[*].id
  description = "Subnet group for LMS RDS isolated from EKS and internet"

  tags = { Name = "${var.cluster_name}-rds-subnet-group" }
}

# MySQL 8.0 Parameter Group — production-tuned settings
resource "aws_db_parameter_group" "lms_mysql" {
  name        = "${var.cluster_name}-mysql80"
  family      = "mysql8.0"
  description = "LMS MySQL 8.0 parameter group"

  # Force SSL connections from the application
  parameter {
    name  = "require_secure_transport"
    value = "ON"
  }

  # Tune InnoDB buffer pool for t3.micro (256MB RAM available for MySQL)
  parameter {
    name  = "innodb_buffer_pool_size"
    value = "{DBInstanceClassMemory*3/4}"
  }

  # Slow query logging — useful for performance debugging
  parameter {
    name  = "slow_query_log"
    value = "1"
  }

  parameter {
    name  = "long_query_time"
    value = "2"
  }

  # UTF8MB4 for full Unicode support
  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }

  tags = { Name = "${var.cluster_name}-mysql80-params" }
}

# Store RDS password in AWS Secrets Manager
resource "aws_secretsmanager_secret" "rds_password" {
  name                    = "${var.cluster_name}/rds/master-password"
  description             = "RDS master password for LMS database"
  recovery_window_in_days = 7

  tags = { Name = "${var.cluster_name}-rds-secret" }
}

resource "aws_secretsmanager_secret_version" "rds_password" {
  secret_id = aws_secretsmanager_secret.rds_password.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_db_instance.lms_mysql.address
    port     = 3306
    dbname   = var.db_name
  })
}

# ── RDS Instance ──────────────────────────────────────────────────────────────
resource "aws_db_instance" "lms_mysql" {
  identifier = "${var.cluster_name}-mysql"

  # Engine
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = var.db_instance_class
  parameter_group_name = aws_db_parameter_group.lms_mysql.name

  # Storage — with auto-scaling
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"         # gp3 is cheaper and faster than gp2
  storage_encrypted     = true          # encrypt at rest using AWS KMS

  # Credentials
  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.lms_rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false        # NEVER expose RDS to internet

  # High Availability
  multi_az = var.db_multi_az

  # Backups
  backup_retention_period = var.db_backup_retention_days
  backup_window           = "03:00-04:00"      # UTC — low traffic window
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # Protection
  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.cluster_name}-mysql-final-snapshot"

  # Performance Insights (free for t3 instances, 7-day retention)
  performance_insights_enabled = false

  # Enhanced Monitoring (1-minute granularity)
  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_monitoring.arn

  # Auto minor version upgrades
  auto_minor_version_upgrade = true

  tags = { Name = "${var.cluster_name}-mysql" }

  depends_on = [
    aws_db_subnet_group.lms_rds,
    aws_db_parameter_group.lms_mysql,
    aws_security_group.rds,
  ]
}

# IAM role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  name = "${var.cluster_name}-rds-monitoring-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
  role       = aws_iam_role.rds_monitoring.name
}

# ─────────────────────────────────────────────────────────────────────────────
# ECR Repository
# ─────────────────────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "lms_app" {
  name                 = "lms-app-ali"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  # Lifecycle policy — keep only the last 10 images to save storage costs
  lifecycle {
    ignore_changes = [tags]
  }

  tags = { Name = "lms-app" }
}

resource "aws_ecr_lifecycle_policy" "lms_app" {
  repository = aws_ecr_repository.lms_app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
