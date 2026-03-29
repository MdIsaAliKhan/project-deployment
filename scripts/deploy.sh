#!/bin/bash
# ============================================================
# scripts/deploy.sh
# Full deployment: Terraform → ECR → EKS → RDS schema import
# Usage: bash scripts/deploy.sh
# ============================================================

set -e

AWS_REGION=${AWS_REGION:-"us-east-1"}
CLUSTER_NAME=${CLUSTER_NAME:-"lms-eks-cluster"}
NAMESPACE="lms"

echo "╔══════════════════════════════════════════════╗"
echo "║   University LMS — Full EKS + RDS Deploy    ║"
echo "╚══════════════════════════════════════════════╝"

# ── STEP 1: Terraform ─────────────────────────────────────
echo ""
echo "[1/7] Provisioning infrastructure with Terraform..."
cd terraform

# Check db_password is set
if [ -z "$TF_VAR_db_password" ]; then
  read -s -p "Enter RDS DB password (min 8 chars): " TF_VAR_db_password
  export TF_VAR_db_password
  echo ""
fi

terraform init
terraform apply -auto-approve

# Capture outputs
ECR_URL=$(terraform output -raw ecr_repository_url)
RDS_HOST=$(terraform output -raw rds_endpoint)
cd ..

echo "    ECR: $ECR_URL"
echo "    RDS: $RDS_HOST"

# ── STEP 2: kubectl config ────────────────────────────────
echo ""
echo "[2/7] Configuring kubectl..."
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"

# ── STEP 3: Build & push Docker image ─────────────────────
echo ""
echo "[3/7] Building and pushing Docker image to ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_URL"

docker build -t lms-app .
docker tag  lms-app:latest "$ECR_URL:latest"
docker push "$ECR_URL:latest"
echo "    Image pushed: $ECR_URL:latest"

# ── STEP 4: Update ConfigMap with RDS endpoint ────────────
echo ""
echo "[4/7] Updating ConfigMap with RDS endpoint..."
sed -i "s|lms-eks-cluster-mysql\..*\.rds\.amazonaws\.com|$RDS_HOST|g" \
  k8s/configmap.yaml
echo "    ConfigMap updated with: $RDS_HOST"

# ── STEP 5: Update deployment image ───────────────────────
echo ""
echo "[5/7] Updating deployment image..."
sed -i "s|PLACEHOLDER_ECR_IMAGE|$ECR_URL:latest|g" k8s/deployment.yaml

# ── STEP 6: Apply Kubernetes manifests ────────────────────
echo ""
echo "[6/7] Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# NOTE: No MySQL pod manifests — RDS replaces them
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f monitoring/prometheus-configmap.yaml
kubectl apply -f monitoring/prometheus.yaml
kubectl apply -f monitoring/grafana.yaml

echo "    Waiting for LMS app rollout..."
kubectl rollout status deployment/lms-app -n "$NAMESPACE" --timeout=300s

# ── STEP 7: Import schema (first time only) ───────────────
echo ""
echo "[7/7] Checking if schema import is needed..."
read -p "Is this a FIRST-TIME deployment? Import schema to RDS? (y/N): " IMPORT_SCHEMA
if [[ "$IMPORT_SCHEMA" =~ ^[Yy]$ ]]; then
  bash scripts/import_schema.sh
fi

# ── Summary ───────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║           DEPLOYMENT COMPLETE                ║"
echo "╚══════════════════════════════════════════════╝"

echo ""
echo "LMS App URL:"
kubectl get svc lms-service -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null \
  || echo "  (wait 2-3 min) → kubectl get svc -n lms"

echo ""
echo "Grafana URL:"
kubectl get svc grafana-service -n "$NAMESPACE" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null \
  || echo "  (wait 2-3 min) → kubectl get svc -n lms"

echo ""
echo "RDS Endpoint:  $RDS_HOST"
echo "All Pods:"
kubectl get pods -n "$NAMESPACE"

echo ""
echo "HPA Status:"
kubectl get hpa -n "$NAMESPACE"
