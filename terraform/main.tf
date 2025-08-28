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

