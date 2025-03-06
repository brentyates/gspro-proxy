# GSPro Proxy

A proxy server for GSPro that enables multiple launch monitors to connect simultaneously to a single GSPro instance.

## Purpose

GSPro's Open API typically supports only one connection at a time. This proxy allows you to:

- Connect two or more launch monitors simultaneously to one GSPro instance
- Intelligently route messages between GSPro and the appropriate launch monitor
- Switch the active launch monitor based on player information
- Create a multiplayer experience using hardware that would normally be limited to single-player

## How It Works

The GSPro Proxy acts as an intermediary between GSPro and multiple launch monitors:

1. The proxy creates a server that emulates the GSPro Connect API
2. Launch monitors connect to the proxy instead of directly to GSPro
3. The proxy maintains a connection to the actual GSPro instance
4. Messages from launch monitors are forwarded to GSPro
5. Responses from GSPro are intelligently routed back to the appropriate launch monitor

The proxy uses player information to determine which launch monitor should be active, allowing for seamless switching between players.

```
Launch Monitor 1 <---> |             | <--->  GSPro
                       | GSPro Proxy |
Launch Monitor 2 <---> |             | 
```

## Features

- Connects to GSPro and multiple launch monitors
- Routes messages between GSPro and launch monitors
- Ensures only one launch monitor is active at a time based on player information
- Configurable player-to-monitor mapping
- Filters out shots from inactive launch monitors

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

Start the proxy server:

```
python main.py [options]
```

### Command Line Options

- `--host`: Host address to bind the proxy server (default: localhost)
- `--port`: Port to bind the proxy server (default: 8888)
- `--gspro-host`: GSPro host address (default: localhost)
- `--gspro-port`: GSPro WebSocket port (default: 921)
- `--debug`: Enable debug logging
- `--config`: Path to configuration file (default: config.json)

## Configuration

### Main Configuration (config.json)

The main configuration file allows you to set default values for the proxy server:

```json
{
    "proxy": {
        "host": "localhost",
        "port": 8888
    },
    "gspro": {
        "host": "localhost",
        "port": 921
    },
    "logging": {
        "debug": false
    }
}
```

### Player-to-Monitor Mapping (player_monitor_config.json)

The player-to-monitor mapping configuration allows you to define rules for determining which launch monitor should be active based on player information:

```json
{
    "player_monitor_rules": [
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
}
```

Each rule consists of:
- `player_attribute`: The attribute in the player information to check (e.g., "Handed", "Club")
- `attribute_value`: The value of the attribute to match (e.g., "RH", "LH", "DR", "PT")
- `monitor_pattern`: A pattern to match in the launch monitor name (e.g., "1", "2", "Driver", "Putter")

The proxy will check each rule in order and activate the first launch monitor that matches. If no rule matches, it will use the first available launch monitor as a fallback.

## Testing

The repository includes test scripts to simulate GSPro and launch monitors:

- `test_gspro_server.py`: Simulates a GSPro server that sends player information and receives shots
- `test_clients.py`: Simulates launch monitors that connect to the proxy and send shots

To run the tests:

1. Start the test GSPro server:
   ```
   python test_gspro_server.py --debug
   ```

2. Start the proxy server:
   ```
   python main.py --gspro-port 8921 --debug
   ```

3. Start the test clients:
   ```
   python test_clients.py --port 8888 --duration 30
   ```

This creates a complete test environment with:
1. A simulated GSPro server
2. The GSPro proxy
3. Simulated launch monitor clients

The test server implements the GSPro Connect API, allowing you to verify proxy functionality without a real GSPro installation.

## Troubleshooting

If you encounter connection issues:
1. Ensure GSPro is running and the Connect API is enabled
2. Check that your firewall allows connections on the configured ports
3. Verify that all devices are on the same network
4. Check the proxy logs for detailed error information

## License

[MIT License](LICENSE)

