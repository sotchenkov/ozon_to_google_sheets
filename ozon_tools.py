import requests
import json

from logs import logger


class Request:
    def __init__(self, token: str, client_id: str):
        self.head = {
            "Client-Id": client_id,
            "Api-Key": token,
        }

    @staticmethod
    def load_request_body(filename: str) -> json:
        logger.check_file_exists(filename)
        with open(filename, 'r') as f:
            return json.dumps(json.load(f))

    def get_data(self, url: str, request_body: json) -> json:
        self.response = requests.post(url, headers=self.head, data=self.load_request_body(request_body))
        logger.check_request(url, self.response.status_code, self.response.text)

        return self.response


class Comparator:
    def __init__(self, google_sheet):
        self.gs = google_sheet

    def check_updates(self, new_response: json) -> list:
        added_operations = self.gs.get_operations()
        new_operations = map(lambda x: x['operation_id'], new_response.json()['result']['operations'])

        new_elements = list(filter(lambda x: str(x) not in added_operations, new_operations))

        logger.check_new_orders(new_elements)

        return new_elements
