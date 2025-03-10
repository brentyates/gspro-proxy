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
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [PROXY] - %(levelname)s - %(message)s',
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
    def __init__(self, reader, writer, name=None):
        self.reader = reader
        self.writer = writer
        self.name = name or str(id(writer))
        self.player_name = None
        self.last_activity = asyncio.get_event_loop().time()
        self.active = False

    async def send_message(self, message: str) -> None:
        """Send a message to the launch monitor"""
        try:
            self.writer.write((message + '\n').encode())
            await self.writer.drain()
            self.last_activity = asyncio.get_event_loop().time()
            logger.debug(f"Sent to launch monitor {self.name}: {message}")
        except Exception as e:
            logger.error(f"Failed to send message to launch monitor {self.name}: {e}")
            raise


class GSProClient:
    """Handles connection to GSPro"""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.connected = False
        self.reconnect_delay = 1  # Start with 1 second delay

    async def connect(self) -> None:
        """Connect to GSPro server"""
        while True:
            try:
                logger.info(f"Attempting to connect to GSPro at {self.host}:{self.port}")
                
                # Use raw TCP connection instead of WebSockets
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self.connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
                logger.info(f"Connected to GSPro at {self.host}:{self.port}")
                return
            except (ConnectionRefusedError, OSError) as e:
                self.connected = False
                logger.error(f"Failed to connect to GSPro: {e}")
                logger.info(f"Retrying in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(30, self.reconnect_delay * 2)  # Exponential backoff

    async def disconnect(self) -> None:
        """Disconnect from GSPro server"""
        if self.writer and self.connected:
            self.writer.close()
            await self.writer.wait_closed()
            self.connected = False
            logger.info("Disconnected from GSPro")

    async def send_message(self, message: str) -> None:
        """Send a message to GSPro"""
        try:
            if not self.connected:
                await self.connect()
            self.writer.write((message + '\n').encode())
            await self.writer.drain()
            logger.debug(f"Sent to GSPro: {message}")
        except Exception as e:
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
        
        # Default configuration
        self.allow_multiple_active_monitors = False
        
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
                    
                    # Load the multiple active monitors setting if present
                    if "allow_multiple_active_monitors" in config:
                        self.allow_multiple_active_monitors = bool(config["allow_multiple_active_monitors"])
                        logger.info(f"Multiple active monitors setting: {self.allow_multiple_active_monitors}")
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

    def add_launch_monitor(self, reader, writer, name=None) -> LaunchMonitor:
        """Add a new launch monitor to the list"""
        # Use provided name or generate one based on the connection ID
        if not name:
            name = f"LM_{len(self.launch_monitors) + 1}"
        
        monitor = LaunchMonitor(reader, writer, name)
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
            if not self.allow_multiple_active_monitors:
                # Traditional behavior: only one active monitor at a time
                if self.active_monitor:
                    self.active_monitor.active = False
                self.active_monitor = monitor
                monitor.active = True
                logger.info(f"Set {monitor.name} as the only active monitor")
            else:
                # Multiple active monitors allowed
                monitor.active = True
                self.active_monitor = monitor  # Still track the most recently activated monitor
                logger.info(f"Set {monitor.name} as an active monitor (multiple active monitors allowed)")

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
            
            # For test mode, forward all messages to GSPro without filtering
            await self.gspro.send_message(message)
            
            # Log based on message type
            if "ShotDataOptions" in msg_data and msg_data.get("ShotDataOptions", {}).get("IsHeartBeat", False):
                logger.debug(f"Forwarded heartbeat from {monitor.name} to GSPro")
            elif "BallData" in msg_data or ("ShotDataOptions" in msg_data and msg_data.get("ShotDataOptions", {}).get("ContainsBallData", False)):
                logger.info(f"Forwarded shot data from {monitor.name} to GSPro")
            else:
                logger.debug(f"Forwarded message from {monitor.name} to GSPro")
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from launch monitor {monitor.name}: {message}")
        except Exception as e:
            logger.error(f"Error handling message from launch monitor {monitor.name}: {e}")
            logger.debug(f"Message was: {message}")

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
                
                if not self.allow_multiple_active_monitors:
                    # Traditional behavior: deactivate all monitors first
                    for monitor in self.launch_monitors:
                        monitor.active = False
                        logger.info(f"Deactivated launch monitor: {monitor.name}")
                
                # Set the determined monitor as active
                if active_monitor:
                    self.set_active_monitor(active_monitor)
                    logger.info(f"Activated launch monitor: {active_monitor.name} for {handedness} player with {club}")
            
            # For test mode, broadcast all messages to all launch monitors
            logger.debug(f"Broadcasting message to all launch monitors")
            for monitor in self.launch_monitors:
                try:
                    await monitor.send_message(message)
                except Exception as e:
                    logger.error(f"Failed to send message to {monitor.name}: {e}")
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from GSPro: {message}")
        except Exception as e:
            logger.error(f"Error handling message from GSPro: {e}")

    async def handle_launch_monitor_connection(self, reader, writer) -> None:
        """Handle a new launch monitor connection"""
        # Extract name from query parameters if available
        name = None
        if hasattr(writer, 'path') and '?' in writer.path:
            query_string = writer.path.split('?', 1)[1]
            params = {k: v for k, v in [param.split('=') for param in query_string.split('&') if '=' in param]}
            name = params.get('name')
            logger.info(f"Launch monitor connected with name parameter: {name}")
        
        # Add the launch monitor to our list
        monitor = self.add_launch_monitor(reader, writer, name)
        logger.info(f"Launch monitor connected: {monitor.name}")
        
        try:
            # Process messages from this launch monitor
            async for message in writer:
                await self.handle_launch_monitor_message(monitor, message.decode('utf-8').strip())
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
                while self.gspro.connected:
                    try:
                        # Read a line from the TCP connection
                        data = await self.gspro.reader.readline()
                        if not data:  # Connection closed
                            logger.error("GSPro connection closed (empty data)")
                            self.gspro.connected = False
                            break
                            
                        message = data.decode('utf-8').strip()
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
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.error(f"Error reading from GSPro: {e}")
                        self.gspro.connected = False
                        break
                    
            except ConnectionRefusedError as e:
                logger.error(f"GSPro connection refused: {e}")
                self.gspro.connected = False
            except OSError as e:
                logger.error(f"Network error with GSPro: {e}")
                self.gspro.connected = False
            except Exception as e:
                logger.error(f"Error listening to GSPro: {e}")
                self.gspro.connected = False
            
            # If we got here, connection was lost - try to reconnect
            logger.info("Will attempt to reconnect to GSPro server in 1 second")
            await asyncio.sleep(1)

    async def start_server(self, host: str, port: int) -> None:
        """Start the proxy server"""
        # Create a TCP server
        self.server = await asyncio.start_server(
            self.handle_client_connected, host, port
        )
        
        logger.info(f"GSPro Proxy Server started on {host}:{port}")
        
        # Start listening for GSPro messages
        asyncio.create_task(self.listen_to_gspro())
        
        # Run the server
        async with self.server:
            await self.server.serve_forever()
            
    async def handle_client_connected(self, reader, writer):
        """Handle a new client connection"""
        addr = writer.get_extra_info('peername')
        logger.info(f"New client connected from {addr}")
        
        # Create a launch monitor for this client
        monitor = self.add_launch_monitor(reader, writer)
        
        try:
            while True:
                data = await reader.readline()
                if not data:  # Connection closed
                    break
                    
                message = data.decode('utf-8').strip()
                await self.handle_launch_monitor_message(monitor, message)
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            self.remove_launch_monitor(monitor)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client disconnected: {monitor.name}")

    async def stop(self) -> None:
        """Stop the proxy server"""
        logger.info("Shutdown signal received, stopping server...")
        
        # Close connection to GSPro
        await self.gspro.disconnect()
        
        # Close all launch monitor connections
        for monitor in self.launch_monitors:
            try:
                monitor.writer.close()
                await monitor.writer.wait_closed()
            except:
                pass
        
        # Close the server
        if hasattr(self, 'server'):
            self.server.close()
            await self.server.wait_closed()
        
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
    parser = argparse.ArgumentParser(description='GSPro Proxy Server')
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
                        help=f'GSPro port (default: {config["gspro"]["port"]})')
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
    
    # Set up logging based on config
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Create the proxy server
    proxy = GSProProxy(args.gspro_host, args.gspro_port)
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(shutdown())
    
    async def shutdown():
        await proxy.stop()
        logger.info("Server shutdown complete")
        loop.stop()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # Start the server
    try:
        await proxy.start_server(args.host, args.port)
    except KeyboardInterrupt:
        await proxy.stop()
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        await proxy.stop()


if __name__ == "__main__":
    asyncio.run(main())

