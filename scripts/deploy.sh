#!/bin/bash
# ============================================================
# deploy.sh — Full deploy script for LMS on AWS EKS
# Run this AFTER terraform apply has completed
# Usage: bash scripts/deploy.sh
# ============================================================

set -e  # stop on any error

AWS_REGION=${AWS_REGION:-"us-east-1"}
CLUSTER_NAME=${CLUSTER_NAME:-"lms-eks-cluster"}
NAMESPACE="lms"

echo "============================================"
echo " University LMS — EKS Deployment Script"
echo "============================================"

# Step 1: Get ECR URL from Terraform output
echo "[1/7] Getting ECR URL from Terraform..."
cd terraform
ECR_URL=$(terraform output -raw ecr_repository_url)
cd ..
echo "     ECR URL: $ECR_URL"

# Step 2: Configure kubectl
echo "[2/7] Configuring kubectl..."
aws eks update-kubeconfig --region $AWS_REGION --name $CLUSTER_NAME

# Step 3: Build and push Docker image
echo "[3/7] Building and pushing Docker image..."
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ECR_URL

docker build -t lms-app .
docker tag  lms-app:latest $ECR_URL:latest
docker push $ECR_URL:latest
echo "     Image pushed: $ECR_URL:latest"

# Step 4: Replace placeholder in deployment.yaml
echo "[4/7] Updating deployment image..."
sed -i "s|PLACEHOLDER_ECR_IMAGE|$ECR_URL:latest|g" k8s/deployment.yaml

# Step 5: Apply all Kubernetes manifests
echo "[5/7] Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/mysql/mysql-pvc.yaml
kubectl apply -f k8s/mysql/mysql-deployment.yaml
kubectl apply -f k8s/mysql/mysql-service.yaml

echo "     Waiting for MySQL to be ready..."
kubectl wait --for=condition=ready pod -l app=mysql \
  -n $NAMESPACE --timeout=180s

# Step 6: Import schema (only first time)
echo "[6/7] Importing database schema..."
MYSQL_POD=$(kubectl get pod -n $NAMESPACE -l app=mysql \
  -o jsonpath='{.items[0].metadata.name}')
kubectl cp schema.sql $NAMESPACE/$MYSQL_POD:/tmp/schema.sql
kubectl exec -n $NAMESPACE $MYSQL_POD -- \
  bash -c "mysql -u root -p\$MYSQL_ROOT_PASSWORD online_exam < /tmp/schema.sql" \
  && echo "     Schema imported OK" \
  || echo "     Schema already exists — skipping"

# Step 7: Deploy app + monitoring
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f monitoring/prometheus-configmap.yaml
kubectl apply -f monitoring/prometheus.yaml
kubectl apply -f monitoring/grafana.yaml

echo "     Waiting for LMS app to be ready..."
kubectl rollout status deployment/lms-app -n $NAMESPACE --timeout=300s

echo ""
echo "============================================"
echo " DEPLOYMENT COMPLETE"
echo "============================================"

echo ""
echo "LMS App URL:"
kubectl get svc lms-service -n $NAMESPACE \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null \
  || echo "  (LoadBalancer provisioning — wait 2-3 min then run: kubectl get svc -n lms)"

echo ""
echo "Grafana Dashboard URL:"
kubectl get svc grafana-service -n $NAMESPACE \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null \
  || echo "  (LoadBalancer provisioning — wait 2-3 min)"

echo ""
echo "HPA Status:"
kubectl get hpa -n $NAMESPACE

echo ""
echo "All Pods:"
kubectl get pods -n $NAMESPACE
