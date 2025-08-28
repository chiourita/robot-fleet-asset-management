#!/bin/bash
# Rollback script to rollback to previous Docker image
# Usage: 
# ./rollback.sh         # Auto rollback to previous image
# ./rollback.sh v1.0.3  # Rollback to specific image

echo "Robot Fleet Rollback"
echo "======================="

# Check if docker is running
if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running. Please start Docker first."
    exit 1
fi

# Get available images
get_available_images() {
    docker images robot-fleet --format "{{.Tag}}" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V -r
}

if [ -n "$1" ]; then
    # Specific version rollback
    VERSION="$1"
    if ! docker image inspect "robot-fleet:$VERSION" >/dev/null 2>&1; then
        echo "Image robot-fleet:$VERSION not found"
        echo "Available images:"
        get_available_images
        exit 1
    fi
    echo "Rolling back to: $VERSION"
else
    # Automatically rollback to previous image
    echo "Finding previous image..."
    AVAILABLE_IMAGES=($(get_available_images))
    
    if [ ${#AVAILABLE_IMAGES[@]} -lt 2 ]; then
        echo "Need at least 2 images for rollback"
        echo "Available images:"
        printf "%s\n" "${AVAILABLE_IMAGES[@]}"
        exit 1
    fi
    
    VERSION="${AVAILABLE_IMAGES[1]}"  # Not current image, second latest
    echo "Rolling back to: $VERSION"
fi

./scripts/deploy.sh "$VERSION"
