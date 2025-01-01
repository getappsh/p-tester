import requests
import time
import random
import json
from datetime import datetime
from prometheus_client import start_http_server, Counter
import os
import logging

# Environment variables
BASE_URL = os.getenv('BASE_URL', 'https://api-getapp-dev.apps.sr.eastus.aroapp.io').rstrip('/')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Prometheus metrics
request_counter = Counter('getapp_requests_total', 'Total API requests', ['endpoint', 'status'])

class APITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.auth_token = None
        self.device_id = f"python-{random.randint(1000, 9999)}"
        self.current_import_request_id = None

    def _make_request(self, method: str, endpoint: str, json_data: dict = None) -> int:
        """Make an API request and return 1 for success, 2 for failure."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {"Content-Type": "application/json"}

        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, json=json_data)

            if 200 <= response.status_code < 300:
                logger.info(f"Request to {endpoint} succeeded with status {response.status_code}")
                request_counter.labels(endpoint=endpoint, status='success').inc()
                return 1
            else:
                logger.error(f"Request to {endpoint} failed with status {response.status_code}")
                request_counter.labels(endpoint=endpoint, status='failure').inc()
                return 2

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to {endpoint} failed with exception: {str(e)}")
            request_counter.labels(endpoint=endpoint, status='exception').inc()
            return 2

    def login(self) -> int:
        """Logs in to the API and returns 1 for success, 2 for failure."""
        username = os.getenv('GETAPP_USERNAME')
        password = os.getenv('GETAPP_PASSWORD')

        if not username or not password:
            logger.error("Missing required environment variables GETAPP_USERNAME or GETAPP_PASSWORD")
            return 2

        response = self._make_request(
            'POST',
            '/api/login',
            {"username": username, "password": password}
        )

        if response == 1:
            self.auth_token = response.json().get('accessToken')
            return 1
        return 2

    def discovery(self) -> int:
        """Runs the discovery test and returns 1 for success, 2 for failure."""
        discovery_data = {
            "discoveryType": "get-map",
            "general": {
                "personalDevice": {
                    "name": "user-1",
                    "idNumber": "idNumber-123",
                    "personalNumber": "personalNumber-123"
                },
                "situationalDevice": {
                    "weather": 23,
                    "bandwidth": 30,
                    "time": datetime.now().isoformat(),
                    "operativeState": True,
                    "power": 94,
                    "location": {"lat": "33.4", "long": "23.3", "alt": "344"}
                },
                "physicalDevice": {
                    "OS": "android",
                    "MAC": "00-B0-D0-63-C2-26",
                    "IP": "129.2.3.4",
                    "ID": self.device_id,
                    "serialNumber": self.device_id,
                    "possibleBandwidth": "Yes",
                    "availableStorage": "38142328832"
                }
            },
            "softwareData": {
                "formation": "yatush",
                "platform": {
                    "name": "Olar",
                    "platformNumber": "1",
                    "virtualSize": 0,
                    "components": []
                }
            },
            "mapData": {
                "productId": "dummy product",
                "productName": "no-name",
                "productVersion": "3",
                "productType": "osm",
                "description": "bla-bla",
                "boundingBox": "1,2,3,4",
                "crs": "WGS84",
                "imagingTimeStart": datetime.now().isoformat(),
                "imagingTimeEnd": datetime.now().isoformat(),
                "creationDate": datetime.now().isoformat(),
                "source": "DJI Mavic",
                "classification": "raster",
                "compartmentalization": "N/A",
                "region": "ME",
                "sensor": "CCD",
                "precisionLevel": "3.14",
                "resolution": "0.12"
            }
        }

        return self._make_request('POST', '/api/device/discover', discovery_data)

    def run_tests(self):
        """Runs all API tests and logs results."""
        tests = {
            'login': self.login,
            'discovery': self.discovery
        }

        results = {}
        for test_name, test_func in tests.items():
            result = test_func()
            results[test_name] = result
            logger.info(f"Test {test_name}: {'Succeeded' if result == 1 else 'Failed'}")

        return results

def main():
    logger.info(f"Starting API tests with BASE_URL: {BASE_URL}")

    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")

    tester = APITester()
    results = tester.run_tests()

    for test_name, result in results.items():
        logger.info(f"Test: {test_name}, Result: {result}")

if __name__ == "__main__":
    main()
