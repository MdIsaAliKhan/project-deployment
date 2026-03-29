#!/bin/bash
# ============================================================
# scripts/import_schema.sh
# Imports schema.sql into RDS via a temporary kubectl pod.
# Run this ONCE after terraform apply and before deploying the app.
# Usage: bash scripts/import_schema.sh
# ============================================================

set -e

NAMESPACE="lms"
RDS_HOST=$(terraform -chdir=terraform output -raw rds_endpoint)
DB_USER=$(terraform -chdir=terraform output -raw rds_username)
DB_NAME="online_exam"

echo "================================================"
echo " Importing schema into RDS"
echo " Host: $RDS_HOST"
echo " DB:   $DB_NAME"
echo "================================================"

# Prompt for password (never hardcode in scripts)
read -s -p "Enter RDS master password: " DB_PASS
echo ""

# Create a temporary pod with MySQL client to run the import
# (EKS nodes can reach RDS; your local machine probably cannot)
kubectl run schema-import \
  --image=mysql:8.0 \
  --restart=Never \
  --namespace=$NAMESPACE \
  --env="MYSQL_PWD=$DB_PASS" \
  --command -- sleep 3600

echo "Waiting for schema-import pod to be ready..."
kubectl wait --for=condition=ready pod/schema-import \
  -n $NAMESPACE --timeout=60s

# Copy schema file into the pod
kubectl cp schema.sql $NAMESPACE/schema-import:/tmp/schema.sql
kubectl cp migrate_tab_switches.sql $NAMESPACE/schema-import:/tmp/migrate.sql

echo "Creating database and importing schema..."
kubectl exec -n $NAMESPACE schema-import -- \
  mysql -h "$RDS_HOST" -u "$DB_USER" -p"$DB_PASS" \
    -e "CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

kubectl exec -n $NAMESPACE schema-import -- \
  mysql -h "$RDS_HOST" -u "$DB_USER" -p"$DB_PASS" \
    "$DB_NAME" < /tmp/schema.sql

kubectl exec -n $NAMESPACE schema-import -- \
  mysql -h "$RDS_HOST" -u "$DB_USER" -p"$DB_PASS" \
    "$DB_NAME" < /tmp/migrate.sql

echo "Schema imported successfully."

# Clean up the temporary pod
kubectl delete pod schema-import -n $NAMESPACE
echo "Temporary pod cleaned up."
echo "================================================"
echo " DONE — RDS is ready for the application"
echo "================================================"
