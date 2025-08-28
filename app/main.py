import os
import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Robot Fleet Management", version="1.0.0")

# Global state
state = {
    "robot_id": None,
    "sensors": [],
    "initialized": False
}

# Basic sensor models
class SensorA(BaseModel):
    type: str = "sensor_a"
    range: float
    wgs84_coordinates: Dict[str, float]
    bit_mask: str

class SensorB(BaseModel):
    type: str = "sensor_b"
    wgs84_coordinates: Dict[str, float]
    speed_km_per_h: float

class SensorC(BaseModel):
    type: str = "sensor_c"
    field_map: str
    battery_pct: float

class RobotConfig(BaseModel):
    robot_id: str
    sensors: List[Dict[str, Any]]

def load_config() -> Dict[str, Any]:
    """Load robot configuration from JSON file"""
    config_path = os.getenv("ROBOT_CONFIG", "/app/config.json")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Basic validation
        if "robot_id" not in config:
            raise ValueError("robot_id is required in configuration")
        
        if "sensors" not in config or not config["sensors"]:
            raise ValueError("At least one sensor is required")
        
        return config
    except FileNotFoundError:
        raise ValueError(f"Configuration file not found: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")

@app.on_event("startup")
async def startup_event():
    """Initialize robot on startup"""
    try:
        config = load_config()
        
        state["robot_id"] = config["robot_id"]
        state["sensors"] = config["sensors"]
        state["initialized"] = True
        
        logger.info(f"Robot {config['robot_id']} initialized with {len(config['sensors'])} sensors")
        
    except Exception as e:
        logger.error(f"Failed to initialize robot: {e}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if not state["initialized"]:
        raise HTTPException(status_code=503, detail="Robot not initialized")
    
    return {
        "status": "healthy",
        "robot_id": state["robot_id"]
    }

@app.get("/status")
async def get_status():
    """Get robot status"""
    if not state["initialized"]:
        raise HTTPException(status_code=503, detail="Robot not initialized")
    
    return {
        "robot_id": state["robot_id"],
        "sensors": state["sensors"],
        "initialized": state["initialized"]
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Robot Fleet Management System",
        "robot_id": state.get("robot_id", "unknown"),
        "status": "running" if state["initialized"] else "initializing"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
