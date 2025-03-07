#!/usr/bin/env python
import asyncio
import json
import logging
import argparse
import random
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [TEST CLIENTS] - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Launch monitor configurations
LAUNCH_MONITORS = [
    {
        "id": 1,
        "name": "Launch Monitor 1",
        "device_id": "LM_1",
        "player_id": 1,  # Associated with Player 1
        "is_active": False  # Will be set to True when this player is active
    },
    {
        "id": 2,
        "name": "Launch Monitor 2",
        "device_id": "LM_2",
        "player_id": 2,  # Associated with Player 2
        "is_active": False  # Will be set to True when this player is active
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

async def read_json_message(reader):
    """Read a JSON message from the stream."""
    try:
        data = await reader.readline()
        if not data:
            return None
        return json.loads(data.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON received: {e}")
        return None

async def launch_monitor_client(host, port, launch_monitor, test_duration):
    """Simulate a launch monitor client using raw TCP"""
    client_id = launch_monitor["id"]
    device_id = launch_monitor["device_id"]
    player_id = launch_monitor["player_id"]
    
    try:
        # Connect to the server
        reader, writer = await asyncio.open_connection(host, port)
        logger.info(f"Client {client_id}: Connected to {host}:{port}")
        
        # Wait for initial player info from GSPro
        try:
            response = await asyncio.wait_for(read_json_message(reader), timeout=5.0)
            if response:
                logger.info(f"Client {client_id}: Received initial message: {json.dumps(response)}")
                
                # Parse the response to check if it's player info
                if response.get("Code") == 201 and "Player" in response:
                    player_info = response.get("Player", {})
                    handedness = player_info.get("handed", "")
                    club = player_info.get("club", "")
                    logger.info(f"Client {client_id}: Received player info - Handedness: {handedness}, Club: {club}")
                    
                    # Determine if this launch monitor should be active based on player info
                    # In this test setup:
                    # - RH (Right-handed) = Player 1 (Launch Monitor 1)
                    # - LH (Left-handed) = Player 2 (Launch Monitor 2)
                    if (handedness == "RH" and player_id == 1) or (handedness == "LH" and player_id == 2):
                        launch_monitor["is_active"] = True
                        logger.info(f"Client {client_id}: This launch monitor is now ACTIVE for {handedness} player with {club}")
                    else:
                        launch_monitor["is_active"] = False
                        logger.info(f"Client {client_id}: This launch monitor is now INACTIVE (waiting for turn)")
        except asyncio.TimeoutError:
            logger.warning(f"Client {client_id}: No initial player info received within timeout")
        
        # Main client loop
        end_time = asyncio.get_event_loop().time() + test_duration
        shot_count = 0
        
        while asyncio.get_event_loop().time() < end_time:
            # Process any pending messages (could be player info updates)
            try:
                response = await asyncio.wait_for(read_json_message(reader), timeout=0.1)
                if response:
                    logger.info(f"Client {client_id}: Received message: {json.dumps(response)}")
                    
                    # Parse the response to check if it's player info
                    if response.get("Code") == 201 and "Player" in response:
                        player_info = response.get("Player", {})
                        handedness = player_info.get("handed", "")
                        club = player_info.get("club", "")
                        logger.info(f"Client {client_id}: Received player info - Handedness: {handedness}, Club: {club}")
                        
                        # Update active status based on player info
                        if (handedness == "RH" and player_id == 1) or (handedness == "LH" and player_id == 2):
                            launch_monitor["is_active"] = True
                            logger.info(f"Client {client_id}: This launch monitor is now ACTIVE for {handedness} player with {club}")
                        else:
                            launch_monitor["is_active"] = False
                            logger.info(f"Client {client_id}: This launch monitor is now INACTIVE (waiting for turn)")
            except asyncio.TimeoutError:
                # No more messages to process
                pass
            
            # If this launch monitor is active, send a shot after a delay
            if launch_monitor["is_active"]:
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
                
                message_json = json.dumps(shot_message)
                writer.write((message_json + '\n').encode())
                await writer.drain()
                logger.info(f"Client {client_id}: Sent shot {shot_count}")
                
                # Wait for shot confirmation
                try:
                    response = await asyncio.wait_for(read_json_message(reader), timeout=2.0)
                    if response:
                        logger.info(f"Client {client_id}: Received shot confirmation: {json.dumps(response)}")
                except asyncio.TimeoutError:
                    logger.warning(f"Client {client_id}: No shot confirmation received within timeout")
                
                # After sending a shot, this launch monitor becomes inactive until next player switch
                launch_monitor["is_active"] = False
                logger.info(f"Client {client_id}: Waiting for next turn...")
            else:
                # If not active, just wait a bit and check for messages again
                await asyncio.sleep(1.0)
                
                # Occasionally send a heartbeat
                if random.random() < 0.2:  # 20% chance to send heartbeat
                    heartbeat = {
                        "DeviceID": device_id,
                        "APIversion": "1",
                        "ShotDataOptions": {
                            "ContainsBallData": False,
                            "ContainsClubData": False,
                            "LaunchMonitorIsReady": True,
                            "LaunchMonitorBallDetected": False,
                            "IsHeartBeat": True
                        }
                    }
                    message_json = json.dumps(heartbeat)
                    writer.write((message_json + '\n').encode())
                    await writer.drain()
                    logger.debug(f"Client {client_id}: Sent heartbeat")
                    
                    # Wait for heartbeat response
                    try:
                        response = await asyncio.wait_for(read_json_message(reader), timeout=1.0)
                        if response:
                            logger.debug(f"Client {client_id}: Received heartbeat response: {json.dumps(response)}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Client {client_id}: No heartbeat response received within timeout")
                
                # Occasionally send a shot even when inactive (to test filtering)
                if random.random() < 0.15:  # 15% chance to send a shot when inactive
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
                    
                    message_json = json.dumps(shot_message)
                    writer.write((message_json + '\n').encode())
                    await writer.drain()
                    logger.info(f"Client {client_id}: Sent shot {shot_count} while INACTIVE (testing filtering)")
                    
                    # Wait for response (should be a rejection)
                    try:
                        response = await asyncio.wait_for(read_json_message(reader), timeout=2.0)
                        if response:
                            logger.info(f"Client {client_id}: Received response to inactive shot: {json.dumps(response)}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Client {client_id}: No response received for inactive shot within timeout")
        
        logger.info(f"Client {client_id}: Test duration completed. Sent {shot_count} shots.")
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        logger.error(f"Client {client_id}: Error - {str(e)}")

async def run_test(host, port, test_duration):
    """Run test with two simulated launch monitors"""
    tasks = [
        launch_monitor_client(host, port, LAUNCH_MONITORS[0], test_duration),
        launch_monitor_client(host, port, LAUNCH_MONITORS[1], test_duration)
    ]
    
    await asyncio.gather(*tasks)

def main():
    parser = argparse.ArgumentParser(description="Test clients for GSPro server with two simulated launch monitors")
    parser.add_argument("--host", default="localhost", help="Host address of the GSPro server")
    parser.add_argument("--port", type=int, default=8921, help="Port of the GSPro server")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    args = parser.parse_args()
    
    logger.info(f"Starting test clients for GSPro server at {args.host}:{args.port}")
    logger.info(f"Test will run for {args.duration} seconds")
    
    asyncio.run(run_test(args.host, args.port, args.duration))
    
    logger.info("Test completed")

if __name__ == "__main__":
    main()

