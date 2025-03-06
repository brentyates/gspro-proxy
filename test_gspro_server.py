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
from typing import Dict, List

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

# Define player profiles
PLAYERS = [
    {
        "id": 1,
        "name": "Player One",
        "handed": "RH",  # Right-handed
        "club": "DR"     # Driver
    },
    {
        "id": 2,
        "name": "Player Two",
        "handed": "LH",  # Left-handed
        "club": "DR"     # Driver
    }
]

class GSProTestServer:
    """Simulates a GSPro server for testing purposes"""
    
    def __init__(self):
        self.clients = set()
        self.active_player_index = 0  # Start with Player 1 (index 0)
        self.shot_count = 0
        self.api_version = "1.0"
        self.clubs = ["DR", "3W", "5W", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "SW", "PT"]
        self.last_shot_time = None
        self.player_switch_delay = 3.0  # Seconds to wait before switching players after a shot
        self.player_info_interval = 5.0  # Send player info every 5 seconds
        
    @property
    def active_player(self):
        """Get the currently active player"""
        return PLAYERS[self.active_player_index]
        
    async def handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a new client connection"""
        client_id = id(websocket)
        self.clients.add(websocket)

        logger.info(f"Client {client_id} connected")
        
        # When a client connects, immediately send player information
        # This simulates GSPro sending player info to launch monitors
        await self.broadcast_player_info()
        
        # Start a task to periodically send player info to this client
        player_info_task = asyncio.create_task(self.periodic_player_info())
        
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
            player_info_task.cancel()
            
    async def periodic_player_info(self) -> None:
        """Periodically send player information to all clients"""
        try:
            while True:
                await asyncio.sleep(self.player_info_interval)
                await self.broadcast_player_info()
                logger.info(f"Sent periodic player info update")
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            logger.error(f"Error in periodic player info task: {e}")

    async def broadcast_player_info(self) -> None:
        """Send current player information to all connected clients"""
        player = self.active_player
        
        # Format the player info message exactly as specified in the GSPro Connect v1 documentation
        player_info = {
            "Code": 201,
            "Message": "GSPro Player Information",
            "Player": {
                "Handed": player["handed"],
                "Club": player["club"]
            }
        }
        
        player_info_json = json.dumps(player_info)
        logger.info(f"Broadcasting player info: Player {player['id']} ({player['handed']}, {player['club']})")
        
        # Broadcast to all clients
        for client in self.clients:
            try:
                await client.send(player_info_json)
                logger.debug(f"Sent player info to client {id(client)}")
            except Exception as e:
                logger.error(f"Failed to send player info to client {id(client)}: {e}")

    async def switch_to_next_player(self) -> None:
        """Switch to the next player and update all clients"""
        # Toggle between player 1 and player 2
        self.active_player_index = (self.active_player_index + 1) % len(PLAYERS)
        
        # Randomly change club occasionally
        if random.random() < 0.3:  # 30% chance to change club
            new_club = random.choice(self.clubs)
            PLAYERS[self.active_player_index]["club"] = new_club
            logger.info(f"Changed club to {new_club} for Player {self.active_player['id']}")
        
        logger.info(f"Switched to Player {self.active_player['id']}")
        
        # Broadcast the updated player info to all clients
        await self.broadcast_player_info()

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
        self.last_shot_time = asyncio.get_event_loop().time()
        
        # Log the shot data
        logger.info(f"Shot {self.shot_count} received from device {device_id} for Player {self.active_player['id']}")
        logger.debug(f"Ball data: {ball_data}")
        
        # Simulate shot processing time
        await asyncio.sleep(0.2)
        
        # Create a GSPro-like response with shot result
        response = {
            "Code": 200,
            "Message": "Shot received successfully"
        }
        
        # Schedule player switch after a delay
        asyncio.create_task(self.delayed_player_switch())
        
        return response
    
    async def delayed_player_switch(self) -> None:
        """Wait for a delay then switch to the next player"""
        await asyncio.sleep(self.player_switch_delay)
        await self.switch_to_next_player()
        
    async def start(self, host: str, port: int) -> None:
        """Start the test GSPro server"""
        server = await websockets.serve(
            self.handle_client,
            host,
            port,
            process_request=self.process_http_request
        )
        
        logger.info(f"GSPro Test Server started on ws://{host}:{port}")
        logger.info(f"Ready to accept connections")
        logger.info(f"Active player: Player {self.active_player['id']} ({self.active_player['handed']}, {self.active_player['club']})")
        
        # Keep the server running
        await server.wait_closed()
    
    async def process_http_request(self, path, request_headers):
        """Handle HTTP requests to provide info about the server"""
        if path == "/info":
            return 200, [("Content-Type", "application/json")], json.dumps({
                "name": "GSPro Test Server",
                "version": self.api_version,
                "clients": len(self.clients),
                "active_player": self.active_player,
                "shots_processed": self.shot_count
            }).encode()
        return None  # Let websockets handle it


def main():
    """Main entry point for the GSPro test server"""
    parser = argparse.ArgumentParser(description="Test GSPro server for development and testing")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind to (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind to (default: {DEFAULT_PORT})")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    server = GSProTestServer()
    
    try:
        asyncio.run(server.start(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
