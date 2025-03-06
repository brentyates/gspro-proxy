#!/usr/bin/env python3
import asyncio
import json
import logging
import argparse
import sys
import random
import websockets
from websockets.server import WebSocketServerProtocol
from datetime import datetime
from typing import Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("gspro_test_server")

# Default settings
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8921  # Changed from 921 to non-privileged port 8921


class GSProTestServer:
    """Simulates a GSPro server for testing purposes"""
    
    def __init__(self):
        self.clients = set()
        self.current_player = None
        self.shot_count = 0
        self.api_version = "1.0"
        self.player_handedness = "RH"  # Default to right-handed
        self.current_club = "DR"  # Default to driver
        
    async def handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a new client connection"""
        client_id = id(websocket)
        self.clients.add(websocket)

        logger.info(f"Client {client_id} connected")
        
        # When a client connects, immediately send player information
        # This simulates GSPro sending player info to launch monitors
        await self.send_player_info_to_client(websocket=websocket)
        
        try:
            async for message in websocket:
                try:
                    # Log the raw message
                    logger.debug(f"Received from client {client_id}: {message}")
                    
                    # Parse the message
                    data = json.loads(message)
                    
                    # Process the message based on what we can determine from it
                    response = None
                    
                    # Check if this is shot data or a heartbeat
                    if "BallData" in data or "ballData" in data or "shotData" in data:
                        # This appears to be shot data
                        response = await self.handle_shot_data(data, websocket)
                    elif "ShotDataOptions" in data and data.get("ShotDataOptions", {}).get("IsHeartBeat", False):
                        # This is a heartbeat message
                        response = {
                            "Code": 200,
                            "Message": "OK - Heartbeat received"
                        }
                    else:
                        # Unknown message type, send generic response
                        response = {
                            "Code": 200,
                            "Message": "OK - Message received"
                        }
                    
                    if response:
                        response_json = json.dumps(response)
                        await websocket.send(response_json)
                        logger.debug(f"Sent to client {client_id}: {response_json}")
                
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from client {client_id}: {message}")
                    await websocket.send(json.dumps({
                        "Code": 501,
                        "Message": "Error - Invalid JSON"
                    }))
                except Exception as e:
                    logger.error(f"Error processing message from client {client_id}: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} disconnected")
        finally:
            self.clients.remove(websocket)

    async def send_player_info_to_client(self, websocket=None) -> None:
        """Send player information to a specific client or all clients"""
        player_info = {
            "Code": 201,
            "Message": "GSPro Player Information",
            "Player": {
                "Handed": self.player_handedness,
                "Club": self.current_club
            }
        }
        
        player_info_json = json.dumps(player_info)
        
        if websocket:
            # Send to specific client
            await websocket.send(player_info_json)
            logger.debug(f"Sent player info to client: {player_info}")
        else:
            # Broadcast to all clients
            for client in self.clients:
                await client.send(player_info_json)
                logger.debug(f"Broadcast player info to all clients: {player_info}")

    async def update_player_club(self, new_club: str) -> None:
        """Update the current club and notify clients"""
        self.current_club = new_club
        logger.info(f"Updated current club to: {new_club}")
        await self.send_player_info_to_client()

    async def handle_shot_data(self, data: Dict, websocket: WebSocketServerProtocol) -> Dict:
        """Process shot data and return appropriate response"""
        # Extract shot information
        device_id = data.get("DeviceID", data.get("deviceID", "unknown_device"))
        shot_number = data.get("ShotNumber", data.get("shotNumber", 0))
        
        # Extract ball data from the appropriate location based on message format
        ball_data = None
        if "BallData" in data:
            ball_data = data.get("BallData", {})
        elif "ballData" in data:
            ball_data = data.get("ballData", {})
        elif "shotData" in data and "ballData" in data.get("shotData", {}):
            ball_data = data.get("shotData", {}).get("ballData", {})
        else:
            ball_data = {}
        
        self.shot_count += 1
        
        # Log the shot data
        logger.info(f"Shot {self.shot_count} received from device {device_id}")
        logger.debug(f"Ball data: {ball_data}")
        
        # Simulate shot processing time
        await asyncio.sleep(0.2)
        
        # Create a GSPro-like response with shot result
        response = {
            "Code": 200,
            "Message": "Shot received successfully"
        }
        
        # After a shot, GSPro might change the club
        # Randomly change club occasionally
        clubs = ["DR", "3W", "5W", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "SW", "PT"]
        if random.random() < 0.4:  # 40% chance to change club after a shot
            self.current_club = random.choice(clubs)
            logger.info(f"Changing club to {self.current_club} after shot")
            
            # Send updated player info to the client that sent the shot
            player_info = {
                "Code": 201,
                "Message": "GSPro Player Information",
                "Player": {
                    "Handed": self.player_handedness,
                    "Club": self.current_club
                }
            }
            
            player_info_json = json.dumps(player_info)
            await websocket.send(player_info_json)
            logger.debug(f"Sent player info after shot: {player_info}")
        
        return response
    
    def _calculate_distance(self, ball_data: Dict) -> float:
        """Calculate total distance based on ball data"""
        # Simple simulation - in reality this would be based on physics
        speed = ball_data.get("speed", 0)
        launch_angle = ball_data.get("verticalAngle", 0)
        
        # Very simplified distance calculation
        return round(speed * 1.5 * (1 + launch_angle/50), 1)
    
    def _calculate_carry(self, ball_data: Dict) -> float:
        """Calculate carry distance based on ball data"""
        # Simplified carry calculation (slightly less than total)
        total = self._calculate_distance(ball_data)
        return round(total * 0.9, 1)
    
    def _calculate_offline(self, ball_data: Dict) -> float:
        """Calculate offline distance based on ball data"""
        # Simple simulation of shot shape based on spin axis and angle
        spin_axis = ball_data.get("spinAxis", 0)
        horizontal_angle = ball_data.get("horizontalAngle", 0)
        
        # Positive is right, negative is left
        return round((spin_axis / 5 + horizontal_angle) * 2, 1)
        
    async def start(self, host: str, port: int) -> None:
        """Start the test GSPro server"""
        server = await websockets.serve(
            self.handle_client,
            host,
            port,
            process_request=self.process_http_request
        )
        
        logger.info(f"GSPro Test Server started on ws://{host}:{port}/GSPro/api/connect")
        logger.info(f"Ready to accept connections")
        
        # Start task to periodically send player updates (simulating GSPro behavior)
        asyncio.create_task(self.periodic_player_updates())
        
        # Keep the server running
        await server.wait_closed()
    
    async def process_http_request(self, path, request_headers):
        """Handle HTTP requests to provide info about the server"""
        if path == "/info":
            return 200, [("Content-Type", "application/json")], json.dumps({
                "name": "GSPro Test Server",
                "version": self.api_version,
                "clients": len(self.clients),
                "current_player": self.current_player,
                "player_handedness": self.player_handedness,
                "current_club": self.current_club,
                "shots_processed": self.shot_count
            }).encode()
        return None  # Let websockets handle it

    async def periodic_player_updates(self) -> None:
        """Periodically send player updates to connected clients"""
        clubs = ["DR", "3W", "5W", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "SW", "PT"]
        while True:
            await asyncio.sleep(30)  # Send updates every 30 seconds
            
            if self.clients:  # Only send if we have connected clients
                # Randomly change club occasionally to simulate GSPro behavior
                if random.random() < 0.3:  # 30% chance to change club
                    self.current_club = random.choice(clubs)
                    logger.info(f"Changing club to {self.current_club}")
                
                await self.send_player_info_to_client()


async def main() -> None:
    """Main entry point for the GSPro test server"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GSPro Test Server')
    parser.add_argument('--host', 
                        default=DEFAULT_HOST,
                        help=f'Host address to bind the server (default: {DEFAULT_HOST})')
    parser.add_argument('--port', type=int, 
                        default=DEFAULT_PORT,
                        help=f'Port to bind the server (default: {DEFAULT_PORT}, note: the real GSPro uses port 921)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set log level based on arguments
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Create and start the server
    server = GSProTestServer()
    
    try:
        await server.start(args.host, args.port)
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Error running server: {e}")


if __name__ == "__main__":
    asyncio.run(main())
