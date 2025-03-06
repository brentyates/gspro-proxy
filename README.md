# GSPro Proxy

A proxy server for GSPro that enables multiple launch monitors to connect simultaneously to a single GSPro instance.

## Purpose

GSPro's Open API typically supports only one connection at a time. This proxy allows you to:

- Connect two launch monitors simultaneously to one GSPro instance
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

## Setup

### Prerequisites
- Python 3.9.4 or higher
- pyenv (recommended for Python version management)

### Installation

1. Clone this repository:
   ```bash
   git clone [repository-url]
   cd gspro-proxy
   ```

2. Set up a Python virtual environment:
   ```bash
   pyenv local 3.9.4  # Optional: if using pyenv
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the GSPro application on your computer

2. Launch the proxy server:
   ```bash
   python main.py
   ```

3. Configure your launch monitors to connect to the proxy instead of directly to GSPro:
   - Use the IP address of the computer running the proxy
   - Use the same port that the proxy is configured to listen on (default: 8888)

4. Start playing! The proxy will handle routing messages between GSPro and your launch monitors.

## Configuration

The proxy can be configured by editing the `config.json` file or using command-line arguments:

```bash
python main.py --port 8888 --gspro-host localhost --gspro-port 0000
```

Common configuration options:
- `port`: The port the proxy listens on for launch monitor connections
- `gspro-host`: The hostname or IP address of the GSPro instance
- `gspro-port`: The port GSPro is listening on
- `debug`: Enable detailed logging for troubleshooting

## Troubleshooting

If you encounter connection issues:
1. Ensure GSPro is running and the Connect API is enabled
2. Check that your firewall allows connections on the configured ports
3. Verify that all devices are on the same network
4. Check the proxy logs for detailed error information

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE)

