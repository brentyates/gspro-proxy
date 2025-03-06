#!/usr/bin/env python3
import asyncio
import json
import logging
import argparse
import sys
import os
from typing import Dict, List, Optional, Any
import websockets
from websockets.exceptions import ConnectionClosed
import aiohttp
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("gspro_proxy")

# Default settings
DEFAULT_HOST = "localhost"
DEFAULT_PROXY_PORT = 8888
DEFAULT_GSPRO_HOST = "localhost"
DEFAULT_GSPRO_PORT = 921


class LaunchMonitor:
    """Represents a connected launch monitor client"""
    def __init__(self, websocket, name=None):
        self.websocket = websocket
        self.name = name or str(id(websocket))
        self.player_name = None
        self.last_activity = asyncio.get_event_loop().time()
        self.active = False

    async def send_message(self, message: str) -> None:
        """Send a message to the launch monitor"""
        try:
            await self.websocket.send(message)
            self.last_activity = asyncio.get_event_loop().time()
            logger.debug(f"Sent to launch monitor {self.name}: {message}")
        except ConnectionClosed:
            logger.error(f"Failed to send message to launch monitor {self.name}, connection closed")
            raise


class GSProClient:
    """Handles connection to GSPro"""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False
        self.reconnect_delay = 1  # Start with 1 second delay

    async def connect(self) -> None:
        """Connect to GSPro server"""
        while True:
            try:
                uri = f"ws://{self.host}:{self.port}/GSPro/api/connect"
                self.websocket = await websockets.connect(uri)
                self.connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
                logger.info(f"Connected to GSPro at {uri}")
                return
            except (ConnectionRefusedError, OSError, websockets.exceptions.WebSocketException) as e:
                self.connected = False
                logger.error(f"Failed to connect to GSPro: {e}")
                logger.info(f"Retrying in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(30, self.reconnect_delay * 2)  # Exponential backoff

    async def disconnect(self) -> None:
        """Disconnect from GSPro server"""
        if self.websocket and self.connected:
            await self.websocket.close()
            self.connected = False
            logger.info("Disconnected from GSPro")

    async def send_message(self, message: str) -> None:
        """Send a message to GSPro"""
        try:
            if not self.connected:
                await self.connect()
            await self.websocket.send(message)
            logger.debug(f"Sent to GSPro: {message}")
        except (ConnectionClosed, websockets.exceptions.WebSocketException) as e:
            logger.error(f"Error sending message to GSPro: {e}")
            self.connected = False
            raise


class GSProProxy:
    """Main proxy server that manages connections and routes messages"""
    def __init__(self, gspro_host: str, gspro_port: int):
        self.launch_monitors: List[LaunchMonitor] = []
        self.gspro = GSProClient(gspro_host, gspro_port)
        self.active_monitor: Optional[LaunchMonitor] = None

    def get_launch_monitor_by_name(self, name: str) -> Optional[LaunchMonitor]:
        """Find a launch monitor by name"""
        for monitor in self.launch_monitors:
            if monitor.name == name:
                return monitor
        return None

    def get_launch_monitor_by_player(self, player_name: str) -> Optional[LaunchMonitor]:
        """Find a launch monitor associated with a player name"""
        for monitor in self.launch_monitors:
            if monitor.player_name == player_name:
                return monitor
        return None

    def add_launch_monitor(self, websocket, name=None) -> LaunchMonitor:
        """Add a new launch monitor connection"""
        monitor = LaunchMonitor(websocket, name)
        self.launch_monitors.append(monitor)
        
        # If this is the first launch monitor, make it active
        if len(self.launch_monitors) == 1:
            self.active_monitor = monitor
            monitor.active = True
            
        logger.info(f"Added launch monitor: {monitor.name}")
        return monitor

    def remove_launch_monitor(self, monitor: LaunchMonitor) -> None:
        """Remove a launch monitor connection"""
        if monitor in self.launch_monitors:
            self.launch_monitors.remove(monitor)
            logger.info(f"Removed launch monitor: {monitor.name}")
            
            # If the active monitor was removed, set the first available as active
            if self.active_monitor == monitor and self.launch_monitors:
                self.active_monitor = self.launch_monitors[0]
                self.active_monitor.active = True
                logger.info(f"Set {self.active_monitor.name} as active monitor")
            elif not self.launch_monitors:
                self.active_monitor = None

    def set_active_monitor(self, monitor: LaunchMonitor) -> None:
        """Set the active launch monitor"""
        if monitor in self.launch_monitors:
            if self.active_monitor:
                self.active_monitor.active = False
            self.active_monitor = monitor
            monitor.active = True
            logger.info(f"Set {monitor.name} as active monitor")

    async def handle_launch_monitor_message(self, monitor: LaunchMonitor, message: str) -> None:
        """Handle messages from a launch monitor"""
        try:
            # Parse the message to see if it contains player information
            msg_data = json.loads(message)
            
            # Check if this is a player info message and update the monitor's player info
            if "PlayerInfo" in msg_data.get("Header", {}).get("MessageType", ""):
                player_name = msg_data.get("PlayerInfo", {}).get("Name", "")
                if player_name:
                    monitor.player_name = player_name
                    # Set this monitor as active since it's sending player info
                    self.set_active_monitor(monitor)
                    logger.info(f"Updated player name for {monitor.name} to {player_name}")
            
            # Forward the message to GSPro
            await self.gspro.send_message(message)
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from launch monitor {monitor.name}: {message}")
        except Exception as e:
            logger.error(f"Error handling message from launch monitor {monitor.name}: {e}")

    async def handle_gspro_message(self, message: str) -> None:
        """Handle messages from GSPro and route to appropriate launch monitor(s)"""
        try:
            # Parse the message to see if it contains player-specific information
            msg_data = json.loads(message)
            
            # Check if the message contains player information
            player_name = None
            msg_type = msg_data.get("Header", {}).get("MessageType", "")
            
            if "PlayerInfo" in msg_type:
                player_name = msg_data.get("PlayerInfo", {}).get("Name", "")
            elif "ShotData" in msg_type:
                player_name = msg_data.get("ShotData", {}).get("PlayerName", "")
            
            # Route the message based on player name or to the active monitor
            target_monitor = None
            
            if player_name:
                # Try to find a monitor with this player name
                target_monitor = self.get_launch_monitor_by_player(player_name)
                logger.debug(f"Message contains player name: {player_name}")
                
            # If we can't find a specific monitor for the player, use the active one
            if not target_monitor and self.active_monitor:
                target_monitor = self.active_monitor
                logger.debug(f"Using active monitor: {target_monitor.name}")
            
            # Send to the specific monitor if found
            if target_monitor:
                await target_monitor.send_message(message)
            else:
                # Broadcast to all monitors if no specific target
                logger.debug("Broadcasting message to all launch monitors")
                for monitor in self.launch_monitors:
                    await monitor.send_message(message)
                    
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from GSPro: {message}")
            # Still try to broadcast invalid messages to all monitors
            for monitor in self.launch_monitors:
                await monitor.send_message(message)
        except Exception as e:
            logger.error(f"Error handling message from GSPro: {e}")

    async def handle_launch_monitor_connection(self, websocket) -> None:
        """Handle a new launch monitor connection"""
        monitor = self.add_launch_monitor(websocket)
        
        try:
            # Ensure we have a connection to GSPro
            if not self.gspro.connected:
                await self.gspro.connect()
                
            # Process messages from the launch monitor
            async for message in websocket:
                logger.debug(f"Received from launch monitor {monitor.name}: {message}")
                await self.handle_launch_monitor_message(monitor, message)
                
        except ConnectionClosed:
            logger.info(f"Launch monitor {monitor.name} disconnected")
        except Exception as e:
            logger.error(f"Error handling launch monitor {monitor.name}: {e}")
        finally:
            self.remove_launch_monitor(monitor)

    async def listen_to_gspro(self) -> None:
        """Listen for messages from GSPro and route them to launch monitors"""
        while True:
            try:
                if not self.gspro.connected:
                    await self.gspro.connect()
                
                # Wait for messages from GSPro
                async for message in self.gspro.websocket:
                    logger.debug(f"Received from GSPro: {message}")
                    await self.handle_gspro_message(message)
                    
            except ConnectionClosed:
                logger.error("GSPro connection closed")
                self.gspro.connected = False
            except Exception as e:
                logger.error(f"Error listening to GSPro: {e}")
                self.gspro.connected = False
            
            # If we got here, connection was lost - try to reconnect
            await asyncio.sleep(1)

    async def start_server(self, host: str, port: int) -> None:
        """Start the proxy server"""
        server = await websockets.serve(
            self.handle_launch_monitor_connection, 
            host, 
            port
        )
        
        logger.info(f"GSPro Proxy Server started on {host}:{port}")
        
        # Start the GSPro listener as a separate task
        asyncio.create_task(self.listen_to_gspro())
        
        # Keep server running
        await server.wait_closed()

    async def stop(self) -> None:
        """Stop the proxy server and clean up connections"""
        tasks = []
        
        # Close connection to GSPro
        if self.gspro:
            tasks.append(self.gspro.disconnect())
            
        # Close connections to all launch monitors
        for monitor in self.launch_monitors:
            try:
                await monitor.websocket.close()
            except:
                pass
                
        self.launch_monitors = []
        self.active_monitor = None
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Proxy server stopped")


def load_config(config_path="config.json") -> Dict[str, Any]:
    """Load configuration from the specified JSON file"""
    config = {
        "proxy": {
            "host": DEFAULT_HOST,
            "port": DEFAULT_PROXY_PORT
        },
        "gspro": {
            "host": DEFAULT_GSPRO_HOST,
            "port": DEFAULT_GSPRO_PORT
        },
        "logging": {
            "debug": False
        }
    }
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                loaded_config = json.load(f)
                # Update our default config with loaded values
                config.update(loaded_config)
                logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.warning(f"Config file {config_path} not found. Using default values.")
    except json.JSONDecodeError:
        logger.error(f"Error parsing {config_path}. Using default values.")
    except Exception as e:
        logger.error(f"Error loading config file: {e}. Using default values.")
        
    return config


async def main() -> None:
    """Main entry point for the GSPro proxy server"""
    # Load configuration from file
    config = load_config()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GSPro WebSocket Proxy Server')
    parser.add_argument('--host', 
                        default=config["proxy"]["host"],
                        help=f'Host address to bind the proxy server (default: {config["proxy"]["host"]})')
    parser.add_argument('--port', type=int, 
                        default=config["proxy"]["port"],
                        help=f'Port to bind the proxy server (default: {config["proxy"]["port"]})')
    parser.add_argument('--gspro-host', 
                        default=config["gspro"]["host"],
                        help=f'GSPro host address (default: {config["gspro"]["host"]})')
    parser.add_argument('--gspro-port', type=int, 
                        default=config["gspro"]["port"],
                        help=f'GSPro WebSocket port (default: {config["gspro"]["port"]})')
    parser.add_argument('--debug', action='store_true',
                        default=config["logging"].get("debug", False),
                        help='Enable debug logging')
    parser.add_argument('--config', 
                        default="config.json",
                        help='Path to configuration file (default: config.json)')
    
    args = parser.parse_args()
    
    # If a custom config file was specified on the command line, reload with that file
    if args.config != "config.json":
        config = load_config(args.config)
        # Re-parse args to allow command line to override the new config file
        parser.set_defaults(
            host=config["proxy"]["host"],
            port=config["proxy"]["port"],
            gspro_host=config["gspro"]["host"],
            gspro_port=config["gspro"]["port"],
            debug=config["logging"].get("debug", False)
        )
        args = parser.parse_args()
    
    # Set log level based on arguments
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Create the proxy
    proxy = GSProProxy(args.gspro_host, args.gspro_port)
    
    # Setup signal handling for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Shutdown signal received, stopping server...")
        stop_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # Start the server task
    server_task = asyncio.create_task(proxy.start_server(args.host, args.port))
    
    # Wait for stop signal
    await stop_event.wait()
    
    # Clean up
    await proxy.stop()
    server_task.cancel()
    
    try:
        await server_task
    except asyncio.CancelledError:
        pass
    
    logger.info("Server shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

