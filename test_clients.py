#!/usr/bin/env python
import asyncio
import json
import logging
import argparse
import random
import websockets
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Sample player data
PLAYERS = [
    {
        "name": "Player One",
        "gender": "MALE",
        "handedness": "RIGHT",
        "clubId": 3,  # Driver
        "launchMonitorName": "Launch Monitor 1"
    },
    {
        "name": "Player Two",
        "gender": "FEMALE",
        "handedness": "LEFT",
        "clubId": 3,  # Driver
        "launchMonitorName": "Launch Monitor 2"
    }
]

# Sample shot data
def generate_shot_data():
    return {
        "ballData": {
            "speed": random.uniform(140.0, 170.0),
            "spinAxis": random.uniform(-15.0, 15.0),
            "totalSpin": random.uniform(2000.0, 3000.0),
            "horizontalAngle": random.uniform(-5.0, 5.0),
            "verticalAngle": random.uniform(10.0, 20.0)
        },
        "clubData": {
            "speed": random.uniform(95.0, 110.0),
            "angleOfAttack": random.uniform(-3.0, 3.0),
            "faceToTarget": random.uniform(-5.0, 5.0),
            "path": random.uniform(-5.0, 5.0)
        }
    }

async def launch_monitor_client(uri, player_data, test_duration, client_id):
    """Simulate a launch monitor client"""
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Client {client_id}: Connected to {uri}")
            
            # Send player information
            player_info = {
                "deviceID": f"simulated_device_{client_id}",
                "shotsCount": 0,
                "shotTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "shotSelected": 0,
                "api": "GSPro Connect v1",
                "units": "Yards",
                "Player": player_data
            }
            
            await websocket.send(json.dumps(player_info))
            logger.info(f"Client {client_id}: Sent player info for {player_data['name']}")
            
            # Wait for response
            response = await websocket.recv()
            logger.info(f"Client {client_id}: Received: {response}")
            
            # Send shot data periodically
            end_time = asyncio.get_event_loop().time() + test_duration
            shot_count = 0
            
            while asyncio.get_event_loop().time() < end_time:
                # Wait a bit between shots
                await asyncio.sleep(random.uniform(5.0, 10.0))
                
                # Generate and send shot data
                shot_count += 1
                shot_data = generate_shot_data()
                shot_message = {
                    "deviceID": f"simulated_device_{client_id}",
                    "shotNumber": shot_count,
                    "shotTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "api": "GSPro Connect v1",
                    "units": "Yards",
                    "shotData": shot_data,
                    "clubData": {
                        "clubId": player_data["clubId"]
                    }
                }
                
                await websocket.send(json.dumps(shot_message))
                logger.info(f"Client {client_id}: Sent shot {shot_count} for {player_data['name']}")
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    logger.info(f"Client {client_id}: Received: {response}")
                except asyncio.TimeoutError:
                    logger.warning(f"Client {client_id}: No response received within timeout")
            
            logger.info(f"Client {client_id}: Test duration completed. Sent {shot_count} shots.")
    except Exception as e:
        logger.error(f"Client {client_id}: Error - {str(e)}")

async def run_test(host, port, test_duration):
    """Run test with two simulated launch monitors"""
    uri = f"ws://{host}:{port}"
    tasks = [
        launch_monitor_client(uri, PLAYERS[0], test_duration, 1),
        launch_monitor_client(uri, PLAYERS[1], test_duration, 2)
    ]
    
    await asyncio.gather(*tasks)

def main():
    parser = argparse.ArgumentParser(description="Test script for GSPro proxy with two simulated launch monitors")
    parser.add_argument("--host", default="localhost", help="Host address of the GSPro proxy")
    parser.add_argument("--port", type=int, default=8888, help="Port of the GSPro proxy")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    args = parser.parse_args()
    
    logger.info(f"Starting test clients for GSPro proxy at {args.host}:{args.port}")
    logger.info(f"Test will run for {args.duration} seconds")
    
    asyncio.run(run_test(args.host, args.port, args.duration))
    
    logger.info("Test completed")

if __name__ == "__main__":
    main()

