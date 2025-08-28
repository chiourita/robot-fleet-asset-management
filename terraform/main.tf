terraform {
  required_version = ">= 1.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
  
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "docker" {}

# Create isolated network for robot communication
resource "docker_network" "robot_network" {
  name   = "robot-network"
  driver = "bridge"
  
  ipam_config {
    subnet = "172.20.0.0/16"
  }

  labels {
    label = "managed-by"
    value = "terraform"
  }
}

resource "docker_container" "prometheus" {
  count = var.enable_monitoring ? 1 : 0
  
  name  = "prometheus"
  image = "prom/prometheus:latest"
  
  ports {
    internal = 9090
    external = 9090
  }
  
  volumes {
    host_path      = abspath("${path.module}/prometheus.yml")
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }
  
  networks_advanced {
    name = docker_network.robot_network.name
  }
  
  restart = "unless-stopped"

  labels {
    label = "managed-by"
    value = "terraform"
  }
  
  labels {
    label = "service"
    value = "monitoring"
  }
}

# Generate Prometheus config file for robot monitoring if enabled
resource "local_file" "prometheus_config" {
  count = var.enable_monitoring ? 1 : 0
  
  filename = "${path.module}/prometheus.yml"
  content = templatefile("${path.module}/prometheus.yml.tpl", {
    robot_targets = ["robot_a:8000", "robot_b:8000", "robot_c:8000"]
  })
}
