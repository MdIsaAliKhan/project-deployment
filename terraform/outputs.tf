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
  description = "ECR repository URL — use this in deployment.yaml image field"
  value       = aws_ecr_repository.lms_app.repository_url
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.lms_vpc.id
}

output "configure_kubectl" {
  description = "Run this command to configure kubectl after apply"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${var.cluster_name}"
}
