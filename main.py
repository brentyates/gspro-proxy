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
                # For the test GSPro server, we don't need the /GSPro/api/connect path
                # Just use the host and port directly
                uri = f"ws://{self.host}:{self.port}"
                logger.info(f"Attempting to connect to GSPro at {uri}")
                
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
        
        # Default player-to-monitor mapping rules
        # This can be overridden by configuration
        self.player_monitor_rules = [
            {
                "player_attribute": "Handed",
                "attribute_value": "RH",
                "monitor_pattern": "1"
            },
            {
                "player_attribute": "Handed",
                "attribute_value": "LH",
                "monitor_pattern": "2"
            }
        ]
        
        # Load custom rules from config if available
        self.load_player_monitor_rules()
        
    def load_player_monitor_rules(self) -> None:
        """Load player-to-monitor mapping rules from configuration"""
        config_path = "player_monitor_config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if "player_monitor_rules" in config and isinstance(config["player_monitor_rules"], list):
                        self.player_monitor_rules = config["player_monitor_rules"]
                        logger.info(f"Loaded {len(self.player_monitor_rules)} player-to-monitor mapping rules from {config_path}")
                    else:
                        logger.warning(f"No valid player_monitor_rules found in {config_path}, using defaults")
            except Exception as e:
                logger.error(f"Error loading player-to-monitor mapping rules from {config_path}: {e}")
                logger.info("Using default player-to-monitor mapping rules")
        else:
            logger.info(f"No {config_path} found, using default player-to-monitor mapping rules")
            
    def determine_active_monitor_for_player(self, player_info: Dict) -> Optional[LaunchMonitor]:
        """Determine which launch monitor should be active based on player information"""
        if not player_info or not self.launch_monitors:
            return None
            
        # Try to match based on configured rules
        for rule in self.player_monitor_rules:
            player_attribute = rule.get("player_attribute")
            attribute_value = rule.get("attribute_value")
            monitor_pattern = rule.get("monitor_pattern")
            
            if not player_attribute or not attribute_value or not monitor_pattern:
                continue
                
            # Check if the player info matches this rule
            if player_info.get(player_attribute) == attribute_value:
                # Find a monitor that matches the pattern
                for monitor in self.launch_monitors:
                    if monitor_pattern in monitor.name:
                        logger.info(f"Rule match: Player with {player_attribute}={attribute_value} mapped to monitor {monitor.name}")
                        return monitor
        
        # If no rule matched or no matching monitor found, use the first monitor as fallback
        if self.launch_monitors:
            logger.warning(f"No matching rule for player {player_info}, using first available monitor as fallback")
            return self.launch_monitors[0]
            
        return None

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
        """Add a new launch monitor to the list"""
        # Use provided name or generate one based on the connection ID
        if not name:
            name = f"LM_{len(self.launch_monitors) + 1}"
        
        monitor = LaunchMonitor(websocket, name)
        self.launch_monitors.append(monitor)
        
        # If this is the first monitor, make it active by default
        if len(self.launch_monitors) == 1:
            self.set_active_monitor(monitor)
        
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
                    
            # Check if this is a shot data message (contains BallData or similar)
            is_shot_data = (
                "BallData" in msg_data or 
                "ballData" in msg_data or 
                "shotData" in msg_data or
                (
                    "ShotDataOptions" in msg_data and 
                    msg_data.get("ShotDataOptions", {}).get("ContainsBallData", False)
                )
            )
            
            # Check if this is a heartbeat message
            is_heartbeat = (
                "ShotDataOptions" in msg_data and 
                msg_data.get("ShotDataOptions", {}).get("IsHeartBeat", False)
            )
            
            # Always forward heartbeat messages
            if is_heartbeat:
                await self.gspro.send_message(message)
                logger.debug(f"Forwarded heartbeat from {monitor.name} to GSPro")
            # For shot data, only forward if this monitor is active
            elif is_shot_data:
                if monitor.active:
                    # This monitor is active, forward the shot data
                    await self.gspro.send_message(message)
                    logger.info(f"Forwarded shot data from active monitor {monitor.name} to GSPro")
                else:
                    # This monitor is not active, log a warning and don't forward
                    logger.warning(f"Ignored shot data from inactive monitor {monitor.name} - not forwarding to GSPro")
                    
                    # Send a response back to the launch monitor indicating the shot was ignored
                    response = {
                        "Code": 400,
                        "Message": "Shot ignored - this launch monitor is not active for the current player"
                    }
                    await monitor.send_message(json.dumps(response))
            else:
                # For other message types, forward to GSPro
                await self.gspro.send_message(message)
                logger.debug(f"Forwarded message from {monitor.name} to GSPro")
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from launch monitor {monitor.name}: {message}")
        except Exception as e:
            logger.error(f"Error handling message from launch monitor {monitor.name}: {e}")

    async def handle_gspro_message(self, message: str) -> None:
        """Handle messages from GSPro and route to appropriate launch monitor(s)"""
        try:
            # Parse the message to see if it contains player-specific information
            msg_data = json.loads(message)
            
            # Check if the message is a player information message (Code 201)
            code = msg_data.get("Code")
            
            if code == 201 and "Player" in msg_data:
                # This is a player information message in GSPro Connect v1 format
                player_info = msg_data.get("Player", {})
                handedness = player_info.get("Handed", "")
                club = player_info.get("Club", "")
                
                logger.info(f"Received player info from GSPro: Handedness={handedness}, Club={club}")
                
                # Use the new method to determine which monitor should be active
                active_monitor = self.determine_active_monitor_for_player(player_info)
                
                # Deactivate all monitors first
                for monitor in self.launch_monitors:
                    monitor.active = False
                    logger.info(f"Deactivated launch monitor: {monitor.name}")
                
                # Set the determined monitor as active
                if active_monitor:
                    self.set_active_monitor(active_monitor)
                    logger.info(f"Activated launch monitor: {active_monitor.name} for {handedness} player with {club}")
                
                # Broadcast player info to all monitors so they know the current state
                logger.info("Broadcasting player info to all launch monitors")
                for monitor in self.launch_monitors:
                    try:
                        await monitor.send_message(message)
                        logger.info(f"Sent player info to {monitor.name}")
                    except Exception as e:
                        logger.error(f"Failed to send player info to {monitor.name}: {e}")
                
                return
                
            # Handle other message types...
            # Check if the message contains player information in other formats
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
        # Extract name from query parameters if available
        name = None
        if hasattr(websocket, 'path') and '?' in websocket.path:
            query_string = websocket.path.split('?', 1)[1]
            params = {k: v for k, v in [param.split('=') for param in query_string.split('&') if '=' in param]}
            name = params.get('name')
            logger.info(f"Launch monitor connected with name parameter: {name}")
        
        # Add the launch monitor to our list
        monitor = self.add_launch_monitor(websocket, name)
        logger.info(f"Launch monitor connected: {monitor.name}")
        
        try:
            # Process messages from this launch monitor
            async for message in websocket:
                await self.handle_launch_monitor_message(monitor, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Launch monitor disconnected: {monitor.name}")
        finally:
            self.remove_launch_monitor(monitor)

    async def listen_to_gspro(self) -> None:
        """Listen for messages from GSPro and route them to launch monitors"""
        while True:
            try:
                if not self.gspro.connected:
                    await self.gspro.connect()
                    logger.info("Successfully connected to GSPro server")
                
                # Wait for messages from GSPro
                async for message in self.gspro.websocket:
                    logger.debug(f"Received from GSPro: {message}")
                    try:
                        # Parse the message to log its type
                        msg_data = json.loads(message)
                        code = msg_data.get("Code")
                        if code:
                            logger.info(f"Received message from GSPro with code {code}")
                    except:
                        pass
                    
                    # Process the message
                    await self.handle_gspro_message(message)
                    
            except ConnectionClosed as e:
                logger.error(f"GSPro connection closed: {e}")
                self.gspro.connected = False
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"WebSocket error with GSPro: {e}")
                self.gspro.connected = False
            except Exception as e:
                logger.error(f"Error listening to GSPro: {e}")
                self.gspro.connected = False
            
            # If we got here, connection was lost - try to reconnect
            logger.info("Will attempt to reconnect to GSPro server in 1 second")
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

