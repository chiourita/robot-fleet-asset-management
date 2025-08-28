import os
import json
import time
import logging
import signal
import sys
from typing import Dict, List, Any, Optional, Union
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ValidationError, Field, validator
from prometheus_client import CollectorRegistry, Gauge, Counter, Info, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
log = logging.getLogger("robot-fleet")

app = FastAPI(title="Robot Fleet Management", version="1.0.0")

# Global state
STATE = {
    "robot_id": None, 
    "sensors": [], 
    "initialized": False,
    "startup_time": None,
    "config_version": None,
    "health_checks": 0,
    "asset_validation_retries": 0,
    "errors": []
}

# Sensor models with validation
class SensorA(BaseModel):
    type: str = "sensor_a"
    range: float
    wgs84_coordinates: Dict[str, float]
    bit_mask: str
    
    @validator('range')
    def validate_range(cls, v):
        if v <= 0:
            raise ValueError('range must be positive')
        return v

class SensorB(BaseModel):
    type: str = "sensor_b"
    wgs84_coordinates: Dict[str, float]
    speed_km_per_h: float
    
    @validator('speed_km_per_h')
    def validate_speed(cls, v):
        if v < 0:
            raise ValueError('speed cannot be negative')
        return v

class SensorC(BaseModel):
    type: str = "sensor_c"
    field_map: str
    battery_pct: float
    
    @validator('battery_pct')
    def validate_battery(cls, v):
        if not 0 <= v <= 100:
            raise ValueError('battery_pct must be between 0 and 100')
        return v

class RobotConfig(BaseModel):
    robot_id: str
    sensors: List[Dict[str, Any]]
    version: Optional[str] = Field(default="1.0.0", description="Configuration version")

def validate_asset_file(file_path: str, asset_type: str) -> bool:
    """Validate that asset files exist and are readable"""
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
            log.error("Asset file not found or not readable.")
            return False
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            log.warning(f"Asset file is empty: {file_path} for {asset_type}")
        return True
    except Exception as e:
        log.error(f"Error validating asset file {file_path} for {asset_type}: {e}")
        return False

def read_secret(robot_id: str, sensor_name: str, secret_key: str = "wgs84_coordinates", retry_count: int = 2, retry_delay: int = 5) -> Union[Dict, str]:
    """Read secret with exponential backoff retry logic"""
    for attempt in range(retry_count):
        try:
            secret_path = f"/run/secrets/{robot_id}"
            if os.path.exists(secret_path):
                with open(secret_path, 'r') as f:
                    secret_data = json.load(f)

                if sensor_name in secret_data and secret_key in secret_data[sensor_name]:
                    return secret_data[sensor_name][secret_key]
                else:
                    raise KeyError(f"Secret {secret_key} not found for sensor {sensor_name} in {robot_id}")
            
            # Fallback to environment variables (for local dev)
            env_key = f"SECRET_{robot_id.upper()}_{sensor_name.upper()}_{secret_key.upper()}"
            env_value = os.getenv(env_key)
            if env_value:
                try:
                    return json.loads(env_value)
                except json.JSONDecodeError:
                    return env_value
            
            if attempt < retry_count - 1:
                backoff_delay = retry_delay * (2 ** attempt)  # exponential backoff
                log.warning(f"Secret {secret_key} for {sensor_name} in {robot_id} not found, "
                           f"retrying in {backoff_delay}s (attempt {attempt+1}/{retry_count})")
                time.sleep(backoff_delay)
        except Exception as e:
            if attempt < retry_count - 1:
                backoff_delay = retry_delay * (2 ** attempt)
                log.warning(f"Error reading secret {secret_key} for {sensor_name} in {robot_id}: {e}, "
                           f"retrying in {backoff_delay}s (attempt {attempt+1}/{retry_count})")
                time.sleep(backoff_delay)

    raise RuntimeError(f"Failed to read secret {secret_key} for {sensor_name} in {robot_id} after {retry_count} attempts")

def resolve_secrets_in_config(config: Dict[str, Any]) -> Dict[str, Any]:
    robot_id = config.get("robot_id", "unknown")
    
    def resolve_value(value, context_sensor_name=None):
        if isinstance(value, str) and value.startswith("SECRET:"):
            # Parse SECRET:robot_id:sensor_name:secret_key format
            parts = value.split(":", 3)
            if len(parts) >= 3:
                secret_robot_id = parts[1]
                secret_sensor_name = parts[2]
                secret_key = parts[3] if len(parts) > 3 else "wgs84_coordinates"
                return read_secret(secret_robot_id, secret_sensor_name, secret_key)
            else:
                raise ValueError(f"Invalid secret format: {value}. Expected SECRET:robot_id:sensor_name:secret_key")
        return value
    
    def parse_dict(obj, sensor_name=None):
        if isinstance(obj, dict):
            return {k: parse_dict(resolve_value(v, sensor_name), sensor_name) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [parse_dict(item, sensor_name) for item in obj]
        else:
            return resolve_value(obj, sensor_name)
    
    if "sensors" in config:
        resolved_sensors = []
        for sensor in config["sensors"]:
            sensor_name = sensor.get("type", "unknown")
            resolved_sensor = parse_dict(sensor, sensor_name)
            resolved_sensors.append(resolved_sensor)
        config["sensors"] = resolved_sensors
    
    return config

def validate_sensor_config(sensor: Dict[str, Any], retry_count: int = 3, retry_delay: int = 5) -> None:
    """Validate individual sensor config and assets with retry logic"""
    sensor_type = sensor.get("type")
    
    if sensor_type == "sensor_a":
        if "bit_mask" not in sensor:
            raise ValueError("sensor_a requires bit_mask field")
        
        bit_mask_path = sensor["bit_mask"]
        
        for attempt in range(retry_count):
            if validate_asset_file(bit_mask_path, "sensor_a bit_mask"):
                break
            if attempt < retry_count - 1:
                STATE["asset_validation_retries"] += 1
                backoff_delay = retry_delay * (2 ** attempt)
                log.warning(f"Asset validation failed for {bit_mask_path}, "
                           f"retrying in {backoff_delay}s (attempt {attempt+1}/{retry_count})")
                time.sleep(backoff_delay)
            else:
                raise ValueError(f"Asset file validation failed for sensor_a bit_mask: {bit_mask_path}")
    
    elif sensor_type == "sensor_b":
        if "speed_km_per_h" not in sensor:
            raise ValueError("sensor_b requires speed_km_per_h field")
    
    elif sensor_type == "sensor_c":
        if "field_map" not in sensor:
            raise ValueError("sensor_c requires field_map field")
        
        field_map_path = sensor["field_map"]
        
        for attempt in range(retry_count):
            if validate_asset_file(field_map_path, "sensor_c field_map"):
                break
            if attempt < retry_count - 1:
                STATE["asset_validation_retries"] += 1
                backoff_delay = retry_delay * (2 ** attempt)
                log.warning(f"Asset validation failed for {field_map_path}, "
                           f"retrying in {backoff_delay}s (attempt {attempt+1}/{retry_count})")
                time.sleep(backoff_delay)
            else:
                raise ValueError(f"Asset file validation failed for sensor_c field_map: {field_map_path}")

def validate_robot_config(config: Dict[str, Any]) -> None:
    if "robot_id" not in config:
        raise ValueError("robot_id is required")
    
    sensors = config.get("sensors", [])
    if not sensors:
        raise ValueError("At least one sensor is required")
    
    valid_sensor_types = {"sensor_a", "sensor_b", "sensor_c"}
    
    for sensor in sensors:
        sensor_type = sensor.get("type")
        if not sensor_type:
            raise ValueError("Sensor missing required 'type' field")
            
        if sensor_type not in valid_sensor_types:
            raise ValueError(f"Invalid sensor type: {sensor_type}")
        
        validate_sensor_config(sensor)

def format_sensor_info(sensor: Dict[str, Any]) -> str:
    """Format sensor info for clean and consistent logging"""
    sensor_type = sensor["type"]
    
    if sensor_type == "sensor_a":
        range_val = sensor.get("range", "N/A")
        bit_mask_path = sensor.get("bit_mask", "N/A")
        return f"sensor_a (range={range_val}, bit_mask={bit_mask_path})"
    
    elif sensor_type == "sensor_b":
        speed = sensor.get("speed_km_per_h", "N/A")
        return f"sensor_b (speed={speed} km/h)"
    
    elif sensor_type == "sensor_c":
        battery = sensor.get("battery_pct", "N/A")
        field_map_path = sensor.get("field_map", "N/A")
        return f"sensor_c (field_map={field_map_path}, battery={battery}%)"
    
    return f"{sensor_type} (unknown configuration)"

@app.on_event("startup")
async def startup_event():
    """Initialize robot on startup"""
    try:
        STATE["startup_time"] = time.time()
        config_path = os.getenv("ROBOT_CONFIG", "/app/config.json") # where config is mounted 
        log.info(f"Loading configuration from: {config_path}")
        
        with open(config_path, 'r') as f:
            raw_config = json.load(f)
        
        validate_robot_config(raw_config)
        
        config = resolve_secrets_in_config(raw_config)
        
        # Store config version if there is one 
        if "version" in config:
            STATE["config_version"] = config["version"]
        
        STATE["robot_id"] = config["robot_id"]
        STATE["sensors"] = config["sensors"]
        STATE["initialized"] = True
        
        sensor_info = [format_sensor_info(sensor) for sensor in config["sensors"]]
        log.info(f"Robot {config['robot_id']} initialized with sensors: {', '.join(sensor_info)}")
        
        # Signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, handle_shutdown)
            
        log.info(f"Robot {config['robot_id']} ready and running")
        
    except Exception as e:
        STATE["errors"].append(str(e))
        log.error(f"Failed to initialize robot: {e}")
        raise

def handle_shutdown(sig, frame):
    log.info(f"Received shutdown signal {sig}, performing graceful shutdown...")
    log.info(f"Robot {STATE.get('robot_id', 'unknown')} shutting down")
    sys.exit(0)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    STATE["errors"].append(error_msg)
    log.error(f"Unhandled exception: {error_msg}")
    return JSONResponse(
        status_code=500,
        content={"detail": error_msg}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and Docker health checks"""
    STATE["health_checks"] += 1
    
    if not STATE["initialized"]:
        raise HTTPException(status_code=503, detail="Robot not initialized")
    
    return {
        "status": "healthy",
        "robot_id": STATE["robot_id"],
        "sensors_count": len(STATE["sensors"]),
        "uptime_seconds": int(time.time() - STATE["startup_time"]) if STATE["startup_time"] else None,
        "config_version": STATE["config_version"]
    }

@app.get("/status")
async def status():
    """Detailed status endpoint"""
    if not STATE["initialized"]:
        raise HTTPException(status_code=503, detail="Robot not initialized")
    
    return {
        "robot_id": STATE["robot_id"],
        "sensors": STATE["sensors"],
        "initialized": STATE["initialized"],
        "uptime_seconds": int(time.time() - STATE["startup_time"]) if STATE["startup_time"] else None,
        "config_version": STATE["config_version"]
    }

@app.get("/metrics")
async def metrics():
    metrics_data = {
        "health_checks": STATE["health_checks"],
        "asset_validation_retries": STATE["asset_validation_retries"],
        "uptime_seconds": int(time.time() - STATE["startup_time"]) if STATE["startup_time"] else None,
        "error_count": len(STATE["errors"]),
        "initialized": STATE["initialized"],
        "sensors_count": len(STATE["sensors"]) if STATE["sensors"] else 0,
        "robot_id": STATE["robot_id"],
        "timestamp": time.time()
    }
    
    log.info(f"METRICS: {json.dumps(metrics_data)}")
    
    return metrics_data

# Prometheus metrics setup according to https://prometheus.io/docs/instrumenting/writing_clientlibs/#metrics
registry = CollectorRegistry()

robot_uptime = Gauge('robot_uptime_seconds', 'Total uptime of the robot in seconds', 
                    ['robot_id'], registry=registry)
robot_sensors = Gauge('robot_sensors_total', 'Total number of sensors configured', 
                     ['robot_id'], registry=registry)
robot_health_checks = Counter('robot_health_checks_total', 'Total number of health checks performed', 
                             ['robot_id'], registry=registry)
robot_errors = Counter('robot_errors_total', 'Total number of errors encountered', 
                      ['robot_id'], registry=registry)
robot_retries = Counter('robot_asset_validation_retries_total', 'Total number of asset validation retries', 
                       ['robot_id'], registry=registry)
robot_initialized = Gauge('robot_initialized', 'Robot initialization status (1 = initialized, 0 = not initialized)', 
                         ['robot_id'], registry=registry)

@app.get("/prometheus")
async def prometheus_metrics():
    """Get metrics in Prometheus format"""
    robot_id = STATE.get("robot_id", "unknown")
    
    # Update Gauge metrics
    uptime = int(time.time() - STATE["startup_time"]) if STATE["startup_time"] else 0
    robot_uptime.labels(robot_id=robot_id).set(uptime)
    robot_sensors.labels(robot_id=robot_id).set(len(STATE["sensors"]) if STATE["sensors"] else 0)
    robot_initialized.labels(robot_id=robot_id).set(1 if STATE["initialized"] else 0)
    
    # Update Counter metrics
    robot_health_checks.labels(robot_id=robot_id)._value._value = STATE["health_checks"]
    robot_errors.labels(robot_id=robot_id)._value._value = len(STATE["errors"])
    robot_retries.labels(robot_id=robot_id)._value._value = STATE["asset_validation_retries"]
    
    # Return metrics in Prometheus format
    return PlainTextResponse(
        generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/init")
async def initialization_info():
    """Print robot initialization message with full resolved configuration
    
    NOTE: In production, I would be hiding this endpoint behind some authentication layer
    since it exposes resolved secret configuration data (like wgs84_coordinates).
    """
    if not STATE["initialized"]:
        raise HTTPException(status_code=503, detail="Robot not initialized yet")
    
    sensor_info = [format_sensor_info(sensor) for sensor in STATE["sensors"]]
    initialization_message = f"Robot {STATE['robot_id']} initialized with sensors: {', '.join(sensor_info)}"
    
    return {
        "robot_id": STATE["robot_id"],
        "initialization_message": initialization_message,
        "config_version": STATE["config_version"],
        "initialized_at": STATE["startup_time"],
        "sensors_configured": len(STATE["sensors"]),
        "sensor_summary": sensor_info,
        "full_resolved_config": {
            "robot_id": STATE["robot_id"],
            "version": STATE["config_version"], 
            "sensors": STATE["sensors"]
        },
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Robot Fleet Management System",
        "robot_id": STATE.get("robot_id", "unknown"),
        "status": "running" if STATE["initialized"] else "initializing",
        "config_version": STATE["config_version"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
