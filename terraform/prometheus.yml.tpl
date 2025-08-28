global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'robot-fleet'
    static_configs:
      - targets: ${jsonencode(robot_targets)}
    metrics_path: '/prometheus'
    scrape_interval: 10s
    scrape_timeout: 5s
    
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
