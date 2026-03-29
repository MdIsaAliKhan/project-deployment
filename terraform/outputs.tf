# ============================================================
# terraform/outputs.tf
# ============================================================

# ── EKS ──────────────────────────────────────────────────────
output "cluster_name" {
  description = "EKS Cluster name"
  value       = aws_eks_cluster.lms_cluster.name
}

output "cluster_endpoint" {
  description = "EKS Cluster API endpoint"
  value       = aws_eks_cluster.lms_cluster.endpoint
}

output "cluster_certificate_authority" {
  description = "EKS Cluster CA data"
  value       = aws_eks_cluster.lms_cluster.certificate_authority[0].data
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repository URL — paste into deployment.yaml"
  value       = aws_ecr_repository.lms_app.repository_url
}

output "configure_kubectl" {
  description = "Run this to configure kubectl after apply"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${var.cluster_name}"
}

# ── RDS ──────────────────────────────────────────────────────
output "rds_endpoint" {
  description = "RDS MySQL endpoint — use this as MYSQL_HOST in K8s ConfigMap"
  value       = aws_db_instance.lms_mysql.address
}

output "rds_port" {
  description = "RDS MySQL port"
  value       = aws_db_instance.lms_mysql.port
}

output "rds_database_name" {
  description = "MySQL database name"
  value       = aws_db_instance.lms_mysql.db_name
}

output "rds_secret_arn" {
  description = "ARN of the Secrets Manager secret holding RDS credentials"
  value       = aws_secretsmanager_secret.rds_password.arn
}

output "rds_username" {
  description = "RDS master username"
  value       = var.db_username
}

output "rds_password_note" {
  description = "How to retrieve the RDS password"
  value       = "aws secretsmanager get-secret-value --secret-id ${aws_secretsmanager_secret.rds_password.name} --region ${var.aws_region}"
}

# ── Network ───────────────────────────────────────────────────
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.lms_vpc.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (EKS nodes)"
  value       = aws_subnet.private[*].id
}

output "rds_subnet_ids" {
  description = "RDS dedicated subnet IDs"
  value       = aws_subnet.rds[*].id
}

# ── Summary ───────────────────────────────────────────────────
output "next_steps" {
  description = "What to do after terraform apply"
  sensitive   = true
  value = <<-EOT
    ═══════════════════════════════════════════════════════
    DEPLOYMENT COMPLETE — Next Steps:
    ═══════════════════════════════════════════════════════
    1. Configure kubectl:
       aws eks update-kubeconfig --region ${var.aws_region} --name ${var.cluster_name}

    2. Update k8s/configmap.yaml  MYSQL_HOST with:
       ${aws_db_instance.lms_mysql.address}

    3. Base64-encode your DB password and update k8s/secret.yaml:
       echo -n "${var.db_password}" | base64

    4. Import schema into RDS:
       bash scripts/import_schema.sh

    5. Deploy to Kubernetes:
       kubectl apply -f k8s/
    ═══════════════════════════════════════════════════════
  EOT
}
