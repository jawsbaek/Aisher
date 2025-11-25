#!/bin/bash
# Run Docker-based integration tests for Aisher
# This script manages the Docker lifecycle and runs integration tests

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Aisher Integration Test Runner${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: docker-compose is not installed${NC}"
    echo "Please install docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Step 1: Start Docker services
echo -e "\n${YELLOW}[1/4] Starting Docker services...${NC}"
docker-compose -f docker-compose.test.yml up -d

# Step 2: Wait for ClickHouse to be ready
echo -e "\n${YELLOW}[2/4] Waiting for ClickHouse to be ready...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker-compose -f docker-compose.test.yml exec -T clickhouse wget --spider -q http://localhost:8123/ping 2>/dev/null; then
        echo -e "${GREEN}✓ ClickHouse is ready${NC}"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 1

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo -e "\n${RED}Error: ClickHouse failed to start within $MAX_RETRIES seconds${NC}"
        echo -e "${YELLOW}Showing container logs:${NC}"
        docker-compose -f docker-compose.test.yml logs clickhouse
        docker-compose -f docker-compose.test.yml down
        exit 1
    fi
done

# Step 3: Run integration tests
echo -e "\n${YELLOW}[3/4] Running integration tests...${NC}"
if uv run pytest tests/test_integration_docker.py -v --integration "$@"; then
    TEST_RESULT=0
    echo -e "\n${GREEN}✓ All integration tests passed${NC}"
else
    TEST_RESULT=$?
    echo -e "\n${RED}✗ Some integration tests failed${NC}"
fi

# Step 4: Cleanup (optional, controlled by flag)
if [ "${KEEP_CONTAINERS}" != "1" ]; then
    echo -e "\n${YELLOW}[4/4] Cleaning up Docker containers...${NC}"
    docker-compose -f docker-compose.test.yml down -v
    echo -e "${GREEN}✓ Cleanup complete${NC}"
else
    echo -e "\n${YELLOW}[4/4] Keeping Docker containers running (KEEP_CONTAINERS=1)${NC}"
    echo -e "${YELLOW}To stop containers manually, run:${NC}"
    echo "  docker-compose -f docker-compose.test.yml down -v"
fi

echo -e "\n${GREEN}========================================${NC}"
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}Integration tests completed successfully!${NC}"
else
    echo -e "${RED}Integration tests failed with exit code $TEST_RESULT${NC}"
fi
echo -e "${GREEN}========================================${NC}"

exit $TEST_RESULT
