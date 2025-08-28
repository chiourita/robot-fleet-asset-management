# Robot Fleet Management System
_Rita Chiou_

This is a containerized app designed for managing a fleet of robots, each equipped with different sensor setups, asset management capabilities, and automated deployment features.
_I will be explaining the architecture, instruction on how to run the app, and future considerations._


## Stack Overview

### Application
**FastAPI:** For its automatic API documentation, built-in validation using Pydantic, and async support.\
**Uvicorn:** ASGI server for production-ready async request handling.

### Containerization
**Docker & Docker Compose:** For containerization, orchestration and local development, with a multi-stage Dockerfile to enhance security where needed.

### Infrastructure
**Terraform:** Infrastructure as Code for network setup and monitoring stack with out of the box resources and providers.\
**Prometheus:** Metrics collection and monitoring with UI for overview and alerting.\
**Docker Secrets:** Secure handling of sensitive configuration data (like GPS coordinates).


**Deployment scripts:** Decided to go with 2 simple bash scripts to automate deployment and manage versions effectively. Deployment is done by adding a patch to the lastest version on docker images and the containers restart on failure. Rollback is done by pulling the previous version available and restarting the containers. In this case, I avoided using git commits for tagging in order not to overcomplicate the assignment's testability.

**Health Checks:** Added a health check endpoint to the FastAPI app to ensure the app is running and restart policies to ensure high availability.

### System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Robot A      │    │    Robot B      │    │    Robot C      │
│   (sensor_a)    │    │  (sensor_b)     │    │ (sensor_a + c)  │
│   Port: 8001    │    │   Port: 8002    │    │   Port: 8003    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │ Robot Network   │
                    │ (172.20.0.0/16) │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Prometheus    │
                    │   Port: 9090    │
                    └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- curl (for health checks)
- Terraform (optional, for infrastructure setup)

### 1. Basic Deployment

```bash
chmod +x scripts/*.sh

./scripts/deploy.sh 
# Or deploy specific version
./scripts/deploy.sh v1.2.0
```

### 2. Verify Deployment

```bash
curl http://localhost:8001/health

# View initialization messages
curl http://localhost:8001/init
```

### 3. Monitor Fleet

For simple logs and metrics run:
```bash
docker-compose logs -f

# Check metrics
curl http://localhost:8001/metrics
curl http://localhost:8002/prometheus  # Prometheus format
```

Otherwise, deploy prometheus and visit http://localhost:9090 where it is hosted:
```bash
terraform apply -var="enable_monitoring=true"
```

## Configuration Management

### Robot Configuration

Each robot is configured via JSON files in the `configs/` directory:

```json
{
  "robot_id": "robot_a",
  "version": "1.0.0",
  "sensors": [
    {
      "type": "sensor_a",
      "range": 120.5,
      "wgs84_coordinates": "SECRET:robot_a:sensor_a:wgs84_coordinates",
      "bit_mask": "/opt/robot/assets/bit_mask.png"
    }
  ]
}
```

with assets (like `bit_mask` and  `field_map`) configured in `assets/robot_i/` and mounted in `/opt/robot/assets` within the container.

### Secrets Management

Sensitive data (like GPS coordinates) is stored separately in `secrets/` and referenced via the `SECRET:robot_id:sensor:key` format:

```json
{
  "sensor_a": {
    "wgs84_coordinates": {
      "latitude": 40.7128,
      "longitude": -74.0060,
      "altitude": 10.5
    }
  }
}
```

## Testing Scenarios

#### 1. Application Crash Recovery
Kill the current container and watch it restart automatically (due to Docker restart policy).

```bash
docker kill robot_a
docker-compose logs -f robot_a
```

#### 2. Configuration Validation / Secret fetch retries
By providing invalid configuration in `configs/robot_a.json`, we should see the robot failing to start and log validation errors.
By providing invalid secret content the app will retry with exponential backoff and then fail gracefully.\
_Note:_ completely missing secret files cause Docker mount failures before the app starts.

#### 3. Version Rollback
Deploy new version, rollback to previous or specific version.
```bash
./scripts/deploy.sh v2.0.0

./scripts/rollback.sh
./scripts/rollback.sh v1.0.0
```

## Extra Features

### Infrastructure Setup with Terraform

```bash
cd terraform/
terraform init
terraform plan
terraform apply

# Enable monitoring stack
terraform apply -var="enable_monitoring=true"
```

### Monitoring with Prometheus

When enabled, `http://localhost:9090` hosts Prometheus which scrapes metrics from all robots:
- Robot uptime and health status
- Sensor counts and config versions
- Error rates and retry attempts

### Health Checks / Observability

- Health Endpoint: `/health`
- Status Endpoint: `/status` - Current robot state
- Metrics Endpoint: `/metrics` - JSON metrics for custom monitoring
- Prometheus Endpoint: `/prometheus` - Prometheus-format metrics
- Init Endpoint: `/init` - Configuration info of robot upon validation

## Future Considerations

_What I would do differently depending on scope_

#### CI/CD Pipeline
**GitHub Actions**: Workflows for automating builds and deployment pipelines. I would implement deployment following GitOps best practices in combination with Github actions to create a CI/CD pipeline and deploy/rollback using commit tags.\
**Docker Registry**: I would use a registry (like AWS ECR) for image versioning\
**Automated Testing**: Unit tests, integration tests if the app was to scale in complexity\
**Branch Protection**: Set rules for PR reviews and passing tests before merging

#### Security Enhancements
**API Authentication**: Implement JWTs or API key auth for the /init endpoint\
**Stricter Secrets Handling**: Enhanced secret management with proper file permissions if needed (for example on asset files)\
**TLS**: HTTPS endpoints with certificates

#### Infrastructure and deployment
**Terraform**: Infrastructure as Code for any required AWS/cloud resources\
**Multi-Environment**: dev/prod with environment-specific docker-compose files and monitoring\
**Blue-Green Deployments**: I would enforce a simple deployment strategy using load balancer switching\
**Centralized Secrets Storage**: S3 or other storage tool with versioned asset management for sensitive values\
**Rollbacks & Image Tags**: I would tag Docker images based on Git commit SHA for easy rollback and traceability

#### Scalability
**Database**: Later on, I would consider PostgreSQL for persistent state, audit logs, and asset metadata\
**Resource Monitoring**: CPU/memory monitoring with automated alerts

#### Observability
**Alerting**: Slack/email alerts for critical failures\
**Log Aggregation**: Structured logging with correlation IDs
