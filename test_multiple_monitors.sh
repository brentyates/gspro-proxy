#!/bin/bash

# Make sure the script is executable
# chmod +x test_multiple_monitors.sh

# Set up terminal colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Multiple Active Monitors Test${NC}"
echo -e "${YELLOW}This test will verify that multiple launch monitors can be active simultaneously${NC}"
echo

# Step 1: Start the test GSPro server in the background
echo -e "${GREEN}Step 1: Starting the test GSPro server...${NC}"
python test_gspro_server.py --debug &
GSPRO_SERVER_PID=$!
echo "Test GSPro server started with PID: $GSPRO_SERVER_PID"
echo "Waiting 2 seconds for the server to initialize..."
sleep 2
echo

# Step 2: Start the proxy server in the background with the correct port
echo -e "${GREEN}Step 2: Starting the proxy server...${NC}"
python main.py --debug --gspro-port 8921 &
PROXY_PID=$!
echo "Proxy server started with PID: $PROXY_PID"
echo "Waiting 2 seconds for the proxy to initialize..."
sleep 2
echo

# Step 3: Run the multiple active monitors test
echo -e "${GREEN}Step 3: Running the multiple active monitors test...${NC}"
python test_multiple_active_monitors.py
echo

# Step 4: Clean up - kill the servers
echo -e "${GREEN}Step 4: Cleaning up...${NC}"
echo "Stopping proxy server (PID: $PROXY_PID)..."
kill $PROXY_PID
echo "Stopping test GSPro server (PID: $GSPRO_SERVER_PID)..."
kill $GSPRO_SERVER_PID
echo

echo -e "${GREEN}Test completed!${NC}"
echo "Check the logs above to verify that both launch monitors were able to send shots to GSPro."
echo "If you see messages like 'Launch monitor LM_1: Sent shot' and 'Launch monitor LM_2: Sent shot',"
echo "then the test was successful and multiple active monitors are working correctly." 