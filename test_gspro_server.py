#!/usr/bin/env python3
import asyncio
import json
import logging
import argparse
import random
import sys
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("gspro_test_server")

# Default settings
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8921

# Define player profiles
players = [
    {"id": 1, "name": "Player One", "handed": "RH", "club": "DR", "distance_to_target": 100},
    {"id": 2, "name": "Player Two", "handed": "LH", "club": "DR", "distance_to_target": 150}
]

def active_player(index):
    """Get the currently active player."""
    return players[index]

async def log_and_send(writer, response):
    """Log the response and send it to the client"""
    response_json = json.dumps(response)
    logger.debug(f"Sending response: {response_json}")
    writer.write(response_json.encode() + b'\n')
    await writer.drain()

async def handle_client(reader, writer):
    """Handle a new client connection using raw TCP."""
    addr = writer.get_extra_info('peername')
    client_id = id(writer)
    logger.info(f"Client {client_id} connected from {addr}")
    
    active_index = 0
    loop = asyncio.get_event_loop()
    
    await log_and_send(writer, {"Code": 201, "Message": "Player Info", "Player": active_player(active_index)})
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                if not data:
                    logger.info(f"Client {client_id} disconnected")
                    break
                
                text_data = data.decode('utf-8', errors='replace')
                try:
                    message = json.loads(text_data)
                    logger.debug(f"Received message: {json.dumps(message)}")
                    
                    if "ShotDataOptions" in message:
                        options = message["ShotDataOptions"]
                        
                        if options.get("ContainsClubData"):
                            await log_and_send(writer, {"Code": 200})
                            await asyncio.sleep(2)
                            continue
                        
                        if options.get("ContainsBallData"):
                            logger.info(f"Shot received from {client_id}: {json.dumps(message, indent=2)}")
                            await log_and_send(writer, {"Code": 200})
                            
                            active_index = (active_index + 1) % len(players)
                            if random.random() < 0.3:
                                players[active_index]["club"] = random.choice(["DR", "3W", "5W", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "SW", "PT"])
                            players[active_index]["distance_to_target"] = random.randint(80, 250)
                            
                            loop.create_task(send_new_player_info(writer, active_index))
                            continue
                        
                        if options.get("IsHeartBeat"):
                            await log_and_send(writer, {"Code": 200, "Message": "Heartbeat Acknowledged"})
                            continue
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {client_id}")
                    await log_and_send(writer, {"Code": 400, "Message": "Invalid JSON"})
            
            except asyncio.TimeoutError:
                continue
    
    except Exception as e:
        logger.error(f"Error with client {client_id}: {e}\n{traceback.format_exc()}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"Connection from {client_id} closed")

async def send_new_player_info(writer, index):
    """Send updated player info after a delay."""
    await asyncio.sleep(3)
    await log_and_send(writer, {"Code": 201, "Message": "Player Info", "Player": active_player(index)})
    logger.info(f"Switched to Player {players[index]['id']}")

async def start_server(host, port):
    """Start the GSPro test server."""
    server = await asyncio.start_server(handle_client, host, port)
    logger.info(f"Server listening on {host}:{port}")
    async with server:
        await server.serve_forever()

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    try:
        asyncio.run(start_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception as e:
        logger.error(f"Server error: {e}\n{traceback.format_exc()}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
