# Infrastructure outputs for application deployment
output "network_info" {
  description = "Robot network information for docker-compose integration"
  value = {
    network_name = docker_network.robot_network.name
    subnet       = "172.20.0.0/16"
    id          = docker_network.robot_network.id
  }
}
