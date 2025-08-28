#!/bin/bash
# Deployment script for robot fleet applications
# Builds and deploys containers from the current commit
# Usage:
# ./scripts/deploy.sh <version>  # Deploy specific version
# ./scripts/deploy.sh            # Auto-increment patch version (if last was v1.0.1, will deploy v1.0.2)

echo "Robot Fleet Deployment Script"
echo "=============================="

# Image versioning - auto-increment patch version unless overridden
if [ -n "$1" ]; then
    VERSION="$1"
    echo "Deploying version: $VERSION (as specified)"
else
    # Normal auto-increment logic
    LATEST=$(docker images robot-fleet --format "{{.Tag}}" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
    
    if [ -n "$LATEST" ]; then
        MAJOR=$(echo $LATEST | cut -d'.' -f1 | sed 's/v//')
        MINOR=$(echo $LATEST | cut -d'.' -f2)
        PATCH=$(echo $LATEST | cut -d'.' -f3)
        NEW_PATCH=$((PATCH + 1))
        VERSION="v${MAJOR}.${MINOR}.${NEW_PATCH}"
        echo "Deploying version: $VERSION (auto-incremented)"
    else
        # No existing versions, start with v1.0.0
        VERSION="v1.0.0"
        echo "Deploying version: $VERSION (first image version)"
    fi
fi

# Check if docker is running
if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker first."
    exit 1
fi

echo "Stopping existing containers..."
docker-compose down 2>/dev/null || true

echo "Checking for port conflicts on 8001-8003..."
for port in 8001 8002 8003; do
    CONTAINER=$(docker ps --format "{{.Names}}" --filter "publish=$port" 2>/dev/null)
    if [ -n "$CONTAINER" ]; then
        echo "Stopping container '$CONTAINER' using port $port"
        docker stop "$CONTAINER" 2>/dev/null || true
    fi
done

# Check if we can use existing image or need to build
if [ -n "$1" ] && docker image inspect "robot-fleet:$VERSION" >/dev/null 2>&1; then
    echo "Using existing image: robot-fleet:$VERSION (true rollback)"
else
    echo "Building robot-fleet:$VERSION..."
    if ! DOCKER_BUILDKIT=0 docker build \
        --build-arg VERSION=$VERSION \
        -t "robot-fleet:$VERSION" \
        -t "robot-fleet:latest" \
        . ; then
        echo "DOCKER BUILD FAILED!"
        echo "Please check Dockerfile and try again."
        exit 1
    fi
    echo "Build completed successfully."
fi

export CONFIG_VERSION=$VERSION
export IMAGE_TAG=$VERSION

echo "Deploying robot fleet..."
docker-compose up -d

echo "Waiting for containers to start..."
sleep 10

echo "Running health checks..."
failed=0
for port in 8001 8002 8003; do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "Robot on port $port: HEALTHY"
    else
        echo "Robot on port $port: FAILED"
        ((failed++))
    fi
done

if [ $failed -eq 0 ]; then
    echo
    echo "DEPLOYMENT SUCCESSFUL!"
    echo "All robots are healthy and running with version: $VERSION"
    echo
    echo "Robot Endpoints:"
    echo "Robot A Init: http://localhost:8001/init"
    echo "Robot B Init: http://localhost:8002/init" 
    echo "Robot C Init: http://localhost:8003/init"
    echo
    echo "Monitoring:"
    echo "Prometheus: http://localhost:9090"
    echo "Metrics: http://localhost:8001/prometheus"
    echo
    echo "Logs:"
    echo "'docker-compose logs -f' for live logs"
else
    echo
    echo "DEPLOYMENT FAILED!"
    echo "$failed robot(s) not responding"
    echo
    echo "Container logs:"
    docker-compose logs
    echo
    echo "To take down failed deployment:"
    echo "docker-compose down"
    echo
    echo "To rollback this failed deployment:"
    echo "./scripts/rollback.sh"
    
    exit 1
fi
