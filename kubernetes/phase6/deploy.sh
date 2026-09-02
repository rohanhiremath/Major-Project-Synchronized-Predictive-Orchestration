#!/bin/bash
#
# Phase 6: Prediction Service Deployment Script
#
# This script builds and deploys the prediction service to Kubernetes
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="prediction-service"
IMAGE_TAG="v1.0.0"
NAMESPACE="default"

echo "=========================================="
echo " Phase 6: Prediction Service Deployment"
echo "=========================================="
echo ""

# Step 1: Check prerequisites
echo "Step 1: Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found${NC}"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl not found${NC}"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}❌ Cannot connect to Kubernetes cluster${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites OK${NC}"
echo ""

# Step 2: Build Docker image
echo "Step 2: Building Docker image..."
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

cd "$(dirname "$0")"
PROJECT_ROOT="../.."

# Build image from project root with proper context
cd ${PROJECT_ROOT}
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} \
    -f kubernetes/phase6/Dockerfile \
    . \
    2>&1 | tee /tmp/docker-build.log | grep -E "Step|Successfully|Error|built" || true

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "${GREEN}✅ Image built successfully${NC}"
else
    echo -e "${RED}❌ Image build failed${NC}"
    echo "Check log: /tmp/docker-build.log"
    exit 1
fi

# Back to phase6 dir
cd kubernetes/phase6

# Check image size
IMAGE_SIZE=$(docker images ${IMAGE_NAME}:${IMAGE_TAG} --format "{{.Size}}")
echo "   Image size: ${IMAGE_SIZE}"
echo ""

# Step 3: Load image to kind (if using kind)
if kubectl config current-context | grep -q "kind"; then
    echo "Step 3: Loading image to kind cluster..."
    kind load docker-image ${IMAGE_NAME}:${IMAGE_TAG}
    echo -e "${GREEN}✅ Image loaded to kind${NC}"
else
    echo "Step 3: Skipping kind load (not a kind cluster)"
fi
echo ""

# Step 4: Create/update namespace
echo "Step 4: Verifying namespace..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✅ Namespace ready${NC}"
echo ""

# Step 5: Apply Kubernetes manifests
echo "Step 5: Deploying to Kubernetes..."

echo "  Creating RBAC..."
kubectl apply -f rbac.yaml

echo "  Creating ConfigMap..."
kubectl apply -f configmap.yaml

echo "  Creating Deployment..."
kubectl apply -f deployment.yaml

echo "  Creating Service..."
kubectl apply -f service.yaml

echo "  Creating ServiceMonitor..."
kubectl apply -f servicemonitor.yaml

echo -e "${GREEN}✅ All resources applied${NC}"
echo ""

# Step 6: Wait for deployment
echo "Step 6: Waiting for deployment to be ready..."
kubectl rollout status deployment/prediction-service -n ${NAMESPACE} --timeout=300s

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Deployment ready${NC}"
else
    echo -e "${YELLOW}⚠️  Deployment timeout - check logs${NC}"
fi
echo ""

# Step 7: Verify deployment
echo "Step 7: Verifying deployment..."

POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=prediction-service -o jsonpath='{.items[0].metadata.name}')

if [ -z "$POD_NAME" ]; then
    echo -e "${RED}❌ No pod found${NC}"
    exit 1
fi

echo "   Pod: ${POD_NAME}"

# Check pod status
POD_STATUS=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.phase}')
echo "   Status: ${POD_STATUS}"

# Check readiness
READY=$(kubectl get pod ${POD_NAME} -n ${NAMESPACE} -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
if [ "$READY" = "True" ]; then
    echo -e "   Ready: ${GREEN}Yes${NC}"
else
    echo -e "   Ready: ${YELLOW}No${NC}"
fi

# Check health endpoint
echo ""
echo "   Testing health endpoint..."
kubectl port-forward -n ${NAMESPACE} ${POD_NAME} 8080:8080 &> /dev/null &
PORT_FORWARD_PID=$!
sleep 3

HEALTH_STATUS=$(curl -s http://localhost:8080/health | jq -r '.status' 2>/dev/null || echo "error")

if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "   Health: ${GREEN}Healthy${NC}"
else
    echo -e "   Health: ${YELLOW}${HEALTH_STATUS}${NC}"
fi

kill $PORT_FORWARD_PID 2>/dev/null || true

echo ""

# Step 8: Show logs
echo "Step 8: Recent logs..."
echo "----------------------------------------"
kubectl logs -n ${NAMESPACE} ${POD_NAME} --tail=20
echo "----------------------------------------"
echo ""

# Step 9: Summary
echo "=========================================="
echo " Deployment Summary"
echo "=========================================="
echo ""
echo "✅ Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "✅ Namespace: ${NAMESPACE}"
echo "✅ Pod: ${POD_NAME}"
echo "✅ Status: ${POD_STATUS}"
echo ""
echo "Useful Commands:"
echo "  View logs:    kubectl logs -f ${POD_NAME}"
echo "  Exec shell:   kubectl exec -it ${POD_NAME} -- /bin/bash"
echo "  Port-forward: kubectl port-forward ${POD_NAME} 8080:8080"
echo "  Metrics:      kubectl port-forward ${POD_NAME} 9090:9090"
echo "  Delete:       kubectl delete -f ."
echo ""
echo "Endpoints:"
echo "  Health:       http://localhost:8080/health"
echo "  Metrics:      http://localhost:8080/metrics-summary"
echo "  Prometheus:   http://localhost:9090/metrics"
echo ""
echo -e "${GREEN}✅ Phase 6 deployment complete!${NC}"
echo ""
echo "Next: Monitor shadow mode for 1 week, then proceed to Phase 7"
echo ""
