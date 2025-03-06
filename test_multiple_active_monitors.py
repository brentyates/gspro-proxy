#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
import websockets
import random
from datetime import datetime
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("test_multiple_active_monitors")

# Test configuration
PROXY_HOST = "localhost"
PROXY_PORT = 8888
TEST_DURATION = 20  # seconds

# Launch monitor configurations
LAUNCH_MONITORS = [
    {
        "name": "LM_1",
        "device_id": "TestLM_1",
        "is_active": True
    },
    {
        "name": "LM_2",
        "device_id": "TestLM_2",
        "is_active": True
    }
]

# GSPro player configurations
PLAYERS = [
    {
        "id": 1,
        "handed": "RH",
        "club": "DR"
    },
    {
        "id": 2,
        "handed": "LH",
        "club": "DR"
    }
]

def generate_shot_data() -> Dict[str, Any]:
    """Generate random shot data"""
    return {
        "Speed": random.uniform(130.0, 170.0),
        "SpinAxis": random.uniform(-20.0, 20.0),
        "TotalSpin": random.uniform(2000.0, 4000.0),
        "HLA": random.uniform(-10.0, 10.0),
        "VLA": random.uniform(10.0, 20.0),
        "CarryDistance": random.uniform(200.0, 300.0)
    }

async def launch_monitor_client(uri: str, launch_monitor: Dict[str, Any]) -> None:
    """Simulate a launch monitor client"""
    device_id = launch_monitor["device_id"]
    name = launch_monitor["name"]
    shot_count = 0
    
    logger.info(f"Starting launch monitor client: {name}")
    
    try:
        async with websockets.connect(uri) as websocket:
            client_id = id(websocket)
            logger.info(f"Launch monitor {name} connected to proxy")
            
            # Send shots periodically
            while True:
                # Wait a bit before sending a shot (simulating player preparation)
                await asyncio.sleep(random.uniform(2.0, 4.0))
                
                # Generate and send shot data
                shot_count += 1
                ball_data = generate_shot_data()
                
                # Format according to GSPro Connect v1 protocol
                shot_message = {
                    "DeviceID": device_id,
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
                logger.info(f"Launch monitor {name}: Sent shot {shot_count}")
                
                # Wait for response
                response = await websocket.recv()
                logger.info(f"Launch monitor {name}: Received response: {response}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Launch monitor {name} disconnected")
    except Exception as e:
        logger.error(f"Error in launch monitor {name}: {e}")

async def mock_gspro_server(websocket, path):
    """Mock GSPro server that responds to messages and sends player info"""
    client_id = id(websocket)
    logger.info(f"Mock GSPro: Client connected")
    
    try:
        # Send initial player info
        player = PLAYERS[0]
        player_info = {
            "Code": 201,
            "Message": "GSPro Player Information",
            "Player": {
                "Handed": player["handed"],
                "Club": player["club"]
            }
        }
        await websocket.send(json.dumps(player_info))
        logger.info(f"Mock GSPro: Sent initial player info")
        
        # Process incoming messages
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Mock GSPro: Received message: {data}")
                
                # Send a success response
                response = {
                    "Code": 200,
                    "Message": "Shot received successfully"
                }
                await websocket.send(json.dumps(response))
                logger.info(f"Mock GSPro: Sent success response")
                
                # Occasionally switch players
                if random.random() < 0.3:  # 30% chance to switch players
                    player_idx = random.randint(0, len(PLAYERS) - 1)
                    player = PLAYERS[player_idx]
                    player_info = {
                        "Code": 201,
                        "Message": "GSPro Player Information",
                        "Player": {
                            "Handed": player["handed"],
                            "Club": player["club"]
                        }
                    }
                    await websocket.send(json.dumps(player_info))
                    logger.info(f"Mock GSPro: Switched to player {player_idx+1}")
                
            except json.JSONDecodeError:
                logger.error(f"Mock GSPro: Invalid JSON received: {message}")
            except Exception as e:
                logger.error(f"Mock GSPro: Error processing message: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Mock GSPro: Client disconnected")
    except Exception as e:
        logger.error(f"Mock GSPro: Error: {e}")

async def run_test():
    """Run the test with multiple active monitors"""
    # Start mock GSPro server
    gspro_server = await websockets.serve(mock_gspro_server, "localhost", 921)
    logger.info("Mock GSPro server started on ws://localhost:921")
    
    # Start proxy server (assuming it's already running)
    logger.info(f"Assuming proxy server is running on ws://{PROXY_HOST}:{PROXY_PORT}")
    
    # Start launch monitor clients
    tasks = []
    for lm in LAUNCH_MONITORS:
        task = asyncio.create_task(
            launch_monitor_client(f"ws://{PROXY_HOST}:{PROXY_PORT}", lm)
        )
        tasks.append(task)
    
    # Run for the specified duration
    logger.info(f"Test will run for {TEST_DURATION} seconds")
    await asyncio.sleep(TEST_DURATION)
    
    # Cancel all tasks
    for task in tasks:
        task.cancel()
    
    # Close the GSPro server
    gspro_server.close()
    await gspro_server.wait_closed()
    
    logger.info("Test completed")

def main():
    """Main entry point"""
    logger.info("Starting multiple active monitors test")
    asyncio.run(run_test())
    logger.info("Test finished")

if __name__ == "__main__":
    main() 