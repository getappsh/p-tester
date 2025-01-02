import requests
import time
import random
import json
from datetime import datetime
from prometheus_client import start_http_server, Counter
import os
import logging
from typing import Optional, Tuple, Dict

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
request_counter = Counter('getapp_requests_total_python', 'Total API requests', ['endpoint', 'status'])

class APITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.auth_token = None
        self.device_id = f"python-{random.randint(1000, 9999)}"
        self.current_import_request_id = None
        self.bbox_array = self._generate_bbox_array()

    def _generate_bbox_array(self) -> list[str]:
        def random_digit():
            return str(random.randint(0, 9))

        bbox_list = []
        for _ in range(1):
            bbox = f"34.472849{random_digit()}{random_digit()},31.519675{random_digit()}{random_digit()}"
            bbox += f",34.476277{random_digit()}{random_digit()},31.522433{random_digit()}{random_digit()}"
            bbox_list.append(bbox)
        return bbox_list

    def _make_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Tuple[Optional[requests.Response], int]:
        """Make an API request and return the response object and 1 for success, 2 for failure."""
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
                return response, 1
            else:
                logger.error(f"Request to {endpoint} failed with status {response.status_code}")
                request_counter.labels(endpoint=endpoint, status='failure').inc()
                return None, 2

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to {endpoint} failed with exception: {str(e)}")
            request_counter.labels(endpoint=endpoint, status='exception').inc()
            return None, 2

    def login(self) -> int:
        """Logs in to the API and returns 1 for success, 2 for failure."""
        username = os.getenv('GETAPP_USERNAME')
        password = os.getenv('GETAPP_PASSWORD')

        if not username or not password:
            logger.error("Missing required environment variables GETAPP_USERNAME or GETAPP_PASSWORD")
            return 2

        response, status = self._make_request(
            'POST',
            '/api/login',
            {"username": username, "password": password}
        )

        if status == 1 and response:
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

        return self._make_request('POST', '/api/device/discover', discovery_data)[1]

    def import_map(self) -> int:
        bbox = random.choice(self.bbox_array)
        import_data = {
            "deviceId": self.device_id,
            "mapProperties": {
                "productName": "python-test",
                "productId": "python-test",
                "zoomLevel": 12,
                "boundingBox": bbox,
                "targetResolution": 0,
                "lastUpdateAfter": 0
            }
        }

        response, status = self._make_request('POST', '/api/map/import/create', import_data)
        if status == 1 and response:
            self.current_import_request_id = response.json().get('importRequestId')
            return 1

        return 2

    def check_import_status(self) -> int:
        if not self.current_import_request_id:
            logger.error("No current import request ID available.")
            return 2

        response, status = self._make_request('GET', f'/api/map/import/status/{self.current_import_request_id}')
        if status == 1 and response:
            import_status = response.json().get('status')
            logger.info(f"Import status: {import_status}")
            return 1 if import_status == 'Done' else 2

        return 2

    def update_download_status(self, status: str = "Start") -> int:
        if not self.current_import_request_id:
            logger.error("No current import request ID available.")
            return 2

        download_status_data = {
            "deviceId": self.device_id,
            "catalogId": self.current_import_request_id,
            "downloadStart": datetime.now().isoformat(),
            "deliveryStatus": status,
            "type": "map"
        }

        _, status = self._make_request('POST', '/api/delivery/updateDownloadStatus', download_status_data)
        return status

    def prepare_delivery(self) -> int:
        if not self.current_import_request_id:
            logger.error("No current import request ID available.")
            return 2

        response, status = self._make_request('POST', '/api/delivery/prepareDelivery', {
            "catalogId": self.current_import_request_id,
            "deviceId": self.device_id,
            "itemType": "map"
        })

        if status == 1 and response:
            prepared_url = response.json().get('url')
            logger.info(f"Prepared delivery URL: {prepared_url}")
            return 1

        return 2

    def run_tests(self):
        """Runs all API tests and logs results."""
        tests = {
            'login': self.login,
            'discovery': self.discovery,
            'import_map': self.import_map,
            'check_import_status': self.check_import_status,
            'prepare_delivery': self.prepare_delivery,
            'update_download_status': lambda: self.update_download_status("Start")
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
    while True:
        results = tester.run_tests()

        for test_name, result in results.items():
            logger.info(f"Test: {test_name}, Result: {result}")

        logger.info("Waiting 5 minutes before the next run...")
        time.sleep(300)  # Wait for 5 minutes

if __name__ == "__main__":
    main()
