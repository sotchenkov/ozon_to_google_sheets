import argparse

from logs import logger
from ozon_tools import Request, Comparator
from json_parser import Parser
from google_sheets_tools import GSpread


def parse_args():
    parcer = argparse.ArgumentParser()
    parcer.add_argument('--ozon_token', type=str, required=True)
    parcer.add_argument('--ozon_id', type=int, required=True)
    parcer.add_argument('--g_cred', type=str, required=True)
    return parcer.parse_args()


def main():
    ozon = Request(parse_args().ozon_token, str(parse_args().ozon_id))
    response = ozon.get_data('https://api-seller.ozon.ru/v3/finance/transaction/list', 'data/request_body.json')

    google_sheet = GSpread(parse_args().g_cred, 'testsheet')

    compare_responses = Comparator(google_sheet).check_updates(response)

    if compare_responses:
        parsed_operations = []

        for element in compare_responses:
            parsed_operations.append(
                list(map(lambda x: x, Parser(response.json(), element).do_parse().__dict__.values())))

        google_sheet.add_a_new_entry(parsed_operations, compare_responses)


if __name__ == '__main__':
    logger.is_running()
    main()
    logger.is_stopped()
