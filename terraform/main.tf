terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }

  # Optional: store state in S3
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "lms/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

# ── Data ──────────────────────────────────────────────────────────────────────
data "aws_availability_zones" "available" {
  state = "available"
}

# ── VPC ───────────────────────────────────────────────────────────────────────
resource "aws_vpc" "lms_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name                                          = "${var.cluster_name}-vpc"
    "kubernetes.io/cluster/${var.cluster_name}"   = "shared"
  }
}

# Public subnets (for Load Balancer)
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.lms_vpc.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                          = "${var.cluster_name}-public-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}"   = "shared"
    "kubernetes.io/role/elb"                      = "1"
  }
}

# Private subnets (for worker nodes)
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.lms_vpc.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name                                          = "${var.cluster_name}-private-${count.index}"
    "kubernetes.io/cluster/${var.cluster_name}"   = "shared"
    "kubernetes.io/role/internal-elb"             = "1"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.lms_vpc.id
  tags   = { Name = "${var.cluster_name}-igw" }
}

# NAT Gateway (for private subnets to reach internet)
resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.cluster_name}-nat" }
}

# Route Tables
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

# ── IAM Roles ─────────────────────────────────────────────────────────────────
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

# ── EKS Cluster ───────────────────────────────────────────────────────────────
resource "aws_eks_cluster" "lms_cluster" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = "1.29"

  vpc_config {
    subnet_ids              = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
    endpoint_public_access  = true
    endpoint_private_access = true
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]

  tags = { Name = var.cluster_name }
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
  ]

  tags = { Name = "${var.cluster_name}-nodes" }
}

# ── ECR Repository ────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "lms_app" {
  name                 = "lms-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "lms-app" }
}

# ── RDS (Cloud Database) ────────────────────────────────────────────
resource "aws_db_subnet_group" "lms_db_subnet" {
  name       = "lms-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "lms-db-subnet"
  }
}

resource "aws_db_instance" "lms_db" {
  identifier         = "lms-db"
  engine             = "mysql"
  instance_class     = "db.t3.micro"
  allocated_storage  = 20

  db_name  = "online_exam"
  username = "admin"
  password = "Admin1234"

  db_subnet_group_name = aws_db_subnet_group.lms_db_subnet.name

  vpc_security_group_ids = []

  publicly_accessible = true
  skip_final_snapshot = true

  tags = {
    Name = "lms-db"
  }
}