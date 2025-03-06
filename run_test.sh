#!/bin/bash

# Make sure the script is executable
# chmod +x run_test.sh

# Set up terminal colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Multiple Active Monitors Test${NC}"
echo -e "${YELLOW}This test will verify that multiple launch monitors can be active simultaneously${NC}"
echo

# Step 1: Start the proxy server in the background
echo -e "${GREEN}Step 1: Starting the proxy server...${NC}"
python main.py --debug &
PROXY_PID=$!
echo "Proxy server started with PID: $PROXY_PID"
echo "Waiting 2 seconds for the proxy to initialize..."
sleep 2
echo

# Step 2: Run the test script
echo -e "${GREEN}Step 2: Running the test script...${NC}"
python test_multiple_active_monitors.py
echo

# Step 3: Clean up - kill the proxy server
echo -e "${GREEN}Step 3: Cleaning up...${NC}"
echo "Stopping proxy server (PID: $PROXY_PID)..."
kill $PROXY_PID
echo

echo -e "${GREEN}Test completed!${NC}"
echo "Check the logs above to verify that both launch monitors were able to send shots to GSPro."
echo "If you see messages like 'Launch monitor LM_1: Received response' and 'Launch monitor LM_2: Received response',"
echo "then the test was successful and multiple active monitors are working correctly." 