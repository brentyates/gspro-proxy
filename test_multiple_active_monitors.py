#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
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
MOCK_GSPRO_PORT = 9921  # Changed from 921 to avoid permission issues
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

async def launch_monitor_client(host: str, port: int, launch_monitor: Dict[str, Any]) -> None:
    """Simulate a launch monitor client using raw TCP"""
    name = launch_monitor["name"]
    device_id = launch_monitor["device_id"]
    
    try:
        # Connect to the proxy
        reader, writer = await asyncio.open_connection(host, port)
        logger.info(f"Launch monitor {name}: Connected to proxy at {host}:{port}")
        
        # Send initial identification message
        identify_message = {
            "DeviceID": device_id,
            "APIversion": "1",
            "DeviceName": name,
            "ShotDataOptions": {
                "ContainsBallData": False,
                "ContainsClubData": False,
                "LaunchMonitorIsReady": True,
                "LaunchMonitorBallDetected": False,
                "IsHeartBeat": False
            }
        }
        
        message_json = json.dumps(identify_message)
        writer.write((message_json + '\n').encode())
        await writer.drain()
        logger.info(f"Launch monitor {name}: Sent identification message")
        
        # Wait for response
        try:
            response = await asyncio.wait_for(read_json_message(reader), timeout=2.0)
            if response:
                logger.info(f"Launch monitor {name}: Received response: {json.dumps(response)}")
        except asyncio.TimeoutError:
            logger.warning(f"Launch monitor {name}: No response received within timeout")
        
        # Main loop - send shots periodically
        shot_count = 0
        end_time = asyncio.get_event_loop().time() + TEST_DURATION
        
        while asyncio.get_event_loop().time() < end_time:
            # Send a shot
            shot_count += 1
            shot_message = {
                "DeviceID": device_id,
                "Units": "Yards",
                "ShotNumber": shot_count,
                "APIversion": "1",
                "BallData": generate_shot_data(),
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
            logger.info(f"Launch monitor {name}: Sent shot {shot_count}")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(read_json_message(reader), timeout=2.0)
                if response:
                    logger.info(f"Launch monitor {name}: Received response: {json.dumps(response)}")
            except asyncio.TimeoutError:
                logger.warning(f"Launch monitor {name}: No response received within timeout")
            
            # Wait before sending next shot
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Occasionally send a heartbeat
            if random.random() < 0.3:  # 30% chance to send heartbeat
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
                logger.debug(f"Launch monitor {name}: Sent heartbeat")
                
                # Wait for heartbeat response
                try:
                    response = await asyncio.wait_for(read_json_message(reader), timeout=1.0)
                    if response:
                        logger.debug(f"Launch monitor {name}: Received heartbeat response: {json.dumps(response)}")
                except asyncio.TimeoutError:
                    logger.warning(f"Launch monitor {name}: No heartbeat response received within timeout")
        
        logger.info(f"Launch monitor {name}: Test completed. Sent {shot_count} shots.")
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        logger.error(f"Launch monitor {name}: Error - {str(e)}")

async def mock_gspro_server():
    """Start a mock GSPro server using raw TCP"""
    server = await asyncio.start_server(
        handle_client, 'localhost', MOCK_GSPRO_PORT
    )
    
    addr = server.sockets[0].getsockname()
    logger.info(f'Mock GSPro server running on {addr}')
    
    async with server:
        await server.serve_forever()

async def handle_client(reader, writer):
    """Handle a client connection to the mock GSPro server"""
    addr = writer.get_extra_info('peername')
    client_id = id(writer)
    logger.info(f"Mock GSPro: Client {client_id} connected from {addr}")
    
    # Send initial player info
    player_index = 0
    player_info = {
        "Code": 201, 
        "Message": "Player Info", 
        "Player": PLAYERS[player_index]
    }
    writer.write((json.dumps(player_info) + '\n').encode())
    await writer.drain()
    logger.info(f"Mock GSPro: Sent initial player info to client {client_id}")
    
    try:
        while True:
            data = await reader.readline()
            if not data:
                logger.info(f"Mock GSPro: Client {client_id} disconnected")
                break
            
            try:
                message = json.loads(data.decode('utf-8'))
                logger.debug(f"Mock GSPro: Received from client {client_id}: {json.dumps(message)}")
                
                # Process the message based on its content
                shot_options = message.get("ShotDataOptions", {})
                
                if shot_options.get("IsHeartBeat", False):
                    # Respond to heartbeat
                    response = {"Code": 200, "Message": "Heartbeat Acknowledged"}
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    logger.debug(f"Mock GSPro: Sent heartbeat response to client {client_id}")
                
                elif shot_options.get("ContainsBallData", False):
                    # Respond to shot data
                    response = {"Code": 200}
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    logger.info(f"Mock GSPro: Received shot from client {client_id}")
                    
                    # Switch player after shot
                    player_index = (player_index + 1) % len(PLAYERS)
                    
                    # Wait a bit before sending new player info
                    await asyncio.sleep(1.0)
                    
                    # Send new player info
                    player_info = {
                        "Code": 201, 
                        "Message": "Player Info", 
                        "Player": PLAYERS[player_index]
                    }
                    writer.write((json.dumps(player_info) + '\n').encode())
                    await writer.drain()
                    logger.info(f"Mock GSPro: Switched to player {PLAYERS[player_index]['id']}")
                
                else:
                    # Generic acknowledgment for other messages
                    response = {"Code": 200}
                    writer.write((json.dumps(response) + '\n').encode())
                    await writer.drain()
                    logger.debug(f"Mock GSPro: Sent generic response to client {client_id}")
                
            except json.JSONDecodeError:
                logger.warning(f"Mock GSPro: Received invalid JSON from client {client_id}")
                response = {"Code": 400, "Message": "Invalid JSON"}
                writer.write((json.dumps(response) + '\n').encode())
                await writer.drain()
    
    except Exception as e:
        logger.error(f"Mock GSPro: Error with client {client_id}: {str(e)}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"Mock GSPro: Connection from client {client_id} closed")

async def run_test():
    """Run the multiple active monitors test"""
    logger.info("Starting multiple active monitors test")
    
    # Start the mock GSPro server
    gspro_task = asyncio.create_task(mock_gspro_server())
    
    # Give the server a moment to start
    await asyncio.sleep(1)
    
    # Start the launch monitor clients
    client_tasks = [
        launch_monitor_client(PROXY_HOST, PROXY_PORT, LAUNCH_MONITORS[0]),
        launch_monitor_client(PROXY_HOST, PROXY_PORT, LAUNCH_MONITORS[1])
    ]
    
    # Wait for clients to complete their test
    await asyncio.gather(*client_tasks)
    
    # Clean up the server
    gspro_task.cancel()
    try:
        await gspro_task
    except asyncio.CancelledError:
        pass
    
    logger.info("Multiple active monitors test completed")

def main():
    """Main entry point"""
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test error: {str(e)}")
        return 1
    return 0

if __name__ == "__main__":
    main() 