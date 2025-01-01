import requests
import time
import random
import json
from datetime import datetime
from prometheus_client import start_http_server, Counter, Gauge, Summary, Histogram
import os
from typing import Dict, List, Optional, Tuple
import logging
from croniter import croniter
import sys

# Environment variables with defaults
SCHEDULE = os.getenv('TEST_SCHEDULE', '*/5 * * * *')  # Default: every 30 minutes
BASE_URL = os.getenv('BASE_URL', 'https://api-getapp-dev.apps.sr.eastus.aroapp.io').rstrip('/')

# Validate cron expression
try:
    croniter(SCHEDULE)
except ValueError as e:
    print(f"Invalid cron expression in TEST_SCHEDULE: {SCHEDULE}")
    print("Format should be: '* * * * *' (minute hour day_of_month month day_of_week)")
    print("Example: '*/30 * * * *' for every 30 minutes")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api_tests.log')
    ]
)
logger = logging.getLogger(__name__)

# Prometheus metrics
request_counter = Counter('getapp_requests_total', 'Total API requests', ['endpoint', 'method'])
request_latency = Histogram('getapp_request_duration_seconds', 'Request latency in seconds', ['endpoint'])
active_requests = Gauge('getapp_active_requests', 'Number of active requests')
request_size = Summary('getapp_request_size_bytes', 'Request size in bytes')

# Failure metrics
failed_requests = Counter('getapp_failed_requests_total', 'Total failed requests', ['endpoint', 'status_code', 'error_type'])
test_failures = Counter('getapp_test_failures_total', 'Total test failures', ['test_name', 'failure_reason'])
download_failures = Counter('getapp_download_failures_total', 'Download failures', ['file_type'])
import_status_failures = Counter('getapp_import_status_failures', 'Import status failures', ['status'])

class APITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.auth_token = None
        self.device_id = f"python-{random.randint(1000, 9999)}"
        self.number_of_unique_maps = 1
        self.bbox_array = self._generate_bbox_array()
        self.current_import_request_id = None

    def _generate_bbox_array(self) -> List[str]:
        def random_digit():
            return str(random.randint(0, 9))

        bbox_list = []
        for _ in range(self.number_of_unique_maps):
            bbox = f"34.472849{random_digit()}{random_digit()},31.519675{random_digit()}{random_digit()}"
            bbox += f",34.476277{random_digit()}{random_digit()},31.522433{random_digit()}{random_digit()}"
            bbox_list.append(bbox)
        return bbox_list

    def _make_request(self, method: str, endpoint: str, json_data: Optional[Dict] = None) -> Tuple[requests.Response, bool]:
        # If the endpoint is a full URL, use it directly
        if endpoint.startswith('http'):
            url = endpoint
        else:
            # Ensure we don't double-slash
            endpoint = endpoint.lstrip('/')
            url = f"{self.base_url}/{endpoint}"

        logger.info(f"Making {method} request to: {url}")  # Add this log
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        active_requests.inc()
        start_time = time.time()
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, json=json_data)
                if json_data:
                    request_size.observe(len(json.dumps(json_data)))

            request_counter.labels(endpoint=endpoint, method=method).inc()
            request_latency.labels(endpoint=endpoint).observe(time.time() - start_time)
            
            if response.status_code >= 400:
                error_type = 'client_error' if response.status_code < 500 else 'server_error'
                failed_requests.labels(
                    endpoint=endpoint,
                    status_code=response.status_code,
                    error_type=error_type
                ).inc()
                logger.error(f"Request failed: {url} - Status: {response.status_code}")
                return response, False
                
            return response, True
            
        except requests.exceptions.RequestException as e:
            failed_requests.labels(
                endpoint=endpoint,
                status_code=0,
                error_type=type(e).__name__
            ).inc()
            logger.error(f"Request failed for URL {url}: {str(e)}")
            return None, False
        finally:
            active_requests.dec()

    def login(self) -> bool:
        username = os.environ.get('GETAPP_USERNAME')
        password = os.environ.get('GETAPP_PASSWORD')
        
        if not username or not password:
            raise ValueError("Missing required environment variables LOGIN_USERNAME or LOGIN_PASSWORD")
            
        response, success = self._make_request(
            'POST',
            '/api/login',
            {
                "username": username,
                "password": password
            }
        )
        
        if success and response:
            self.auth_token = response.json().get('accessToken')
            return True
        
        test_failures.labels(test_name='login', failure_reason='auth_failed').inc()
        return False

    def discovery(self) -> bool:
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
        
        _, success = self._make_request('POST', '/api/device/discover', discovery_data)
        if not success:
            test_failures.labels(test_name='discovery', failure_reason='api_error').inc()
        return success

    def import_map(self) -> bool:
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
        
        response, success = self._make_request('POST', '/api/map/import/create', import_data)
        if success and response:
            self.current_import_request_id = response.json().get('importRequestId')
            return self.update_download_status(self.current_import_request_id)
        
        test_failures.labels(test_name='import_map', failure_reason='create_failed').inc()
        return False

    def check_import_status(self) -> str:
        if not self.current_import_request_id:
            test_failures.labels(test_name='import_status', failure_reason='no_request_id').inc()
            return 'Error'

        response, success = self._make_request(
            'GET',
            f'/api/map/import/status/{self.current_import_request_id}'
        )
        
        if not success or not response:
            import_status_failures.labels(status='api_error').inc()
            return 'Error'

        status = response.json().get('status')
        if status not in ['Done', 'Error']:
            import_status_failures.labels(status=status).inc()
        
        return status

    def update_download_status(self, catalog_id: str, status: str = "Start") -> bool:
        data = {
            "deviceId": self.device_id,
            "catalogId": catalog_id,
            "downloadStart": datetime.now().isoformat(),
            "bitNumber": 0,
            "downloadData": 32,
            "currentTime": datetime.now().isoformat(),
            "deliveryStatus": status,
            "type": "map"
        }
        
        _, success = self._make_request('POST', '/api/delivery/updateDownloadStatus', data)
        if not success:
            test_failures.labels(
                test_name='update_download_status',
                failure_reason=f'status_update_failed_{status}'
            ).inc()
        return success

    def prepare_delivery(self) -> Optional[str]:
        prepare_data = {
            "catalogId": self.current_import_request_id,
            "deviceId": self.device_id,
            "itemType": "map"
        }
        
        _, success = self._make_request('POST', '/api/delivery/prepareDelivery', prepare_data)
        if not success:
            test_failures.labels(test_name='prepare_delivery', failure_reason='preparation_failed').inc()
            return None

        response, success = self._make_request(
            'GET',
            f'/api/delivery/preparedDelivery/{self.current_import_request_id}'
        )
        
        if not success or not response:
            test_failures.labels(test_name='prepare_delivery', failure_reason='get_url_failed').inc()
            return None

        url = response.json().get('url')
        # If the URL is relative, make it absolute
        if url and not url.startswith('http'):
            if url.startswith('/'):
                url = f"{self.base_url}{url}"
            else:
                url = f"{self.base_url}/{url}"
        
        logger.info(f"Prepared delivery URL: {url}")  # Add this log
        return url

    def download_files(self, url: str) -> bool:
        if not url:
            test_failures.labels(test_name='download_files', failure_reason='no_url').inc()
            return False

        logger.info(f"Attempting to download from URL: {url}")  # Add this log

        try:
            # Download .gpkg file
            _, success_gpkg = self._make_request('GET', url)
            if not success_gpkg:
                logger.error(f"Failed to download .gpkg file from {url}")
                download_failures.labels(file_type='gpkg').inc()

            # Download .json file
            json_url = url.replace('.gpkg', '.json')
            logger.info(f"Attempting to download JSON from URL: {json_url}")  # Add this log
            _, success_json = self._make_request('GET', json_url)
            if not success_json:
                logger.error(f"Failed to download .json file from {json_url}")
                download_failures.labels(file_type='json').inc()

            return success_gpkg and success_json

        except Exception as e:
            logger.error(f"Exception during download: {str(e)}")
            return False

    def update_inventory(self) -> bool:
        inventory_data = {
            "deviceId": self.device_id,
            "inventory": {self.current_import_request_id: "delivery"}
        }
        
        _, success = self._make_request('POST', '/api/map/inventory/updates', inventory_data)
        if not success:
            test_failures.labels(test_name='update_inventory', failure_reason='update_failed').inc()
        return success

    def check_health(self) -> bool:
        endpoints = [
            '/api/delivery/checkHealth',
            '/api/device/checkHealth',
            '/api/offering/checkHealth',
            '/api/map/checkHealth'
        ]
        
        all_healthy = True
        for endpoint in endpoints:
            _, success = self._make_request('GET', endpoint)
            if not success:
                test_failures.labels(test_name='health_check', failure_reason=endpoint).inc()
                all_healthy = False
        
        return all_healthy

    def run_full_test(self):
        logger.info(f"Starting test run with device ID: {self.device_id}")

        # Login
        if not self.login():
            logger.error("Login failed")
            return

        # Discovery
        if not self.discovery():
            logger.error("Discovery failed")
            return

        # Import Map
        if not self.import_map():
            logger.error("Map import failed")
            return

        # Check import status
        status = 'Processing'
        max_retries = 30  # Prevent infinite loop
        retry_count = 0
        while status not in ['Done', 'Error'] and retry_count < max_retries:
            status = self.check_import_status()
            if status == 'Error':
                logger.error("Import status check failed")
                return
            retry_count += 1
            time.sleep(2)

        # Update download status
        self.update_download_status(self.current_import_request_id)

        # Prepare delivery
        download_url = self.prepare_delivery()
        if not download_url:
            logger.error("Prepare delivery failed")
            return

        # Download files
        if not self.download_files(download_url):
            logger.error("File download failed")
            return

        # Update download status multiple times
        for _ in range(5):
            self.update_download_status(self.current_import_request_id)
            time.sleep(2)

        # Update inventory
        if not self.update_inventory():
            logger.error("Inventory update failed")
            return

        # Health checks
        if not self.check_health():
            logger.error("Health checks failed")
            return

        logger.info("All tests completed successfully")

def wait_until_next_run():
    cron = croniter(SCHEDULE, datetime.now())
    next_run = cron.get_next(datetime)
    wait_time = (next_run - datetime.now()).total_seconds()
    
    if wait_time > 0:
        logger.info(f"Waiting until next scheduled run at {next_run}")
        time.sleep(wait_time)

def main():
    logger.info(f"Starting API test script with schedule: {SCHEDULE}")
    logger.info(f"Using BASE_URL: {BASE_URL}")
    
    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")
    
    while True:
        try:
            tester = APITester()
            tester.run_full_test()
        except Exception as e:
            logger.error(f"Error during test run: {str(e)}")
            test_failures.labels(test_name='run_full_test', failure_reason='unexpected_error').inc()
        
        wait_until_next_run()

if __name__ == "__main__":
    main()