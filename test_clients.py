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
        "Speed": random.uniform(140.0, 170.0),
        "SpinAxis": random.uniform(-15.0, 15.0),
        "TotalSpin": random.uniform(2000.0, 3000.0),
        "HLA": random.uniform(-5.0, 5.0),
        "VLA": random.uniform(10.0, 20.0),
        "CarryDistance": random.uniform(220.0, 280.0)
    }

async def launch_monitor_client(uri, player_data, test_duration, client_id):
    """Simulate a launch monitor client"""
    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"Client {client_id}: Connected to {uri}")
            
            # We don't send player information anymore as per GSPro protocol
            # Instead, we wait to receive player info from GSPro
            
            # Wait for initial player info from GSPro
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"Client {client_id}: Received initial message: {response}")
                
                # Parse the response to check if it's player info
                try:
                    resp_data = json.loads(response)
                    if resp_data.get("Code") == 201 and "Player" in resp_data:
                        player_info = resp_data.get("Player", {})
                        logger.info(f"Client {client_id}: Received player info - Handedness: {player_info.get('Handed')}, Club: {player_info.get('Club')}")
                except json.JSONDecodeError:
                    logger.warning(f"Client {client_id}: Received invalid JSON: {response}")
            except asyncio.TimeoutError:
                logger.warning(f"Client {client_id}: No initial player info received within timeout")
            
            # Send shot data periodically
            end_time = asyncio.get_event_loop().time() + test_duration
            shot_count = 0
            
            while asyncio.get_event_loop().time() < end_time:
                # Wait a bit between shots
                await asyncio.sleep(random.uniform(5.0, 10.0))
                
                # Generate and send shot data
                shot_count += 1
                ball_data = generate_shot_data()
                
                # Format according to GSPro Connect v1 protocol
                shot_message = {
                    "DeviceID": f"simulated_device_{client_id}",
                    "Units": "Yards",
                    "ShotNumber": shot_count,
                    "APIversion": "1",
                    "BallData": ball_data,
                    "ClubData": {
                        "Speed": random.uniform(95.0, 110.0),
                        "AngleOfAttack": random.uniform(-3.0, 3.0),
                        "FaceToTarget": random.uniform(-5.0, 5.0),
                        "Path": random.uniform(-5.0, 5.0)
                    },
                    "ShotDataOptions": {
                        "ContainsBallData": True,
                        "ContainsClubData": True,
                        "LaunchMonitorIsReady": True,
                        "LaunchMonitorBallDetected": True,
                        "IsHeartBeat": False
                    }
                }
                
                await websocket.send(json.dumps(shot_message))
                logger.info(f"Client {client_id}: Sent shot {shot_count}")
                
                # Process all responses (could be shot confirmation and player info)
                try:
                    while True:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        logger.info(f"Client {client_id}: Received: {response}")
                        
                        # Parse the response to check if it's player info
                        try:
                            resp_data = json.loads(response)
                            if resp_data.get("Code") == 201 and "Player" in resp_data:
                                player_info = resp_data.get("Player", {})
                                logger.info(f"Client {client_id}: Received player info - Handedness: {player_info.get('Handed')}, Club: {player_info.get('Club')}")
                        except json.JSONDecodeError:
                            logger.warning(f"Client {client_id}: Received invalid JSON: {response}")
                except asyncio.TimeoutError:
                    # No more messages to process
                    pass
                
                # Send heartbeat occasionally
                if random.random() < 0.3:  # 30% chance to send heartbeat
                    heartbeat = {
                        "DeviceID": f"simulated_device_{client_id}",
                        "APIversion": "1",
                        "ShotDataOptions": {
                            "ContainsBallData": False,
                            "ContainsClubData": False,
                            "LaunchMonitorIsReady": True,
                            "LaunchMonitorBallDetected": False,
                            "IsHeartBeat": True
                        }
                    }
                    await websocket.send(json.dumps(heartbeat))
                    logger.debug(f"Client {client_id}: Sent heartbeat")
                    
                    # Wait for heartbeat response
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        logger.debug(f"Client {client_id}: Received heartbeat response: {response}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Client {client_id}: No heartbeat response received within timeout")
            
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

