import os

from logs import logger
from ozon_tools import Request, Comparator
from json_parser import Parser
from google_sheets_tools import GSpread


def main(event, context):
    ozon = Request(os.environ['OZON_TOKEN'], str(os.environ['OZON_ID']))
    response = ozon.get_data('https://api-seller.ozon.ru/v3/finance/transaction/list', 'data/request_body.json')

    google_sheet = GSpread(os.environ['GOOGLE_CREDS'], os.environ['GOOGLE_TABLE_NAME'], os.environ['GOOGLE_SHEET_NAME'])

    compare_responses = Comparator(google_sheet).check_updates(response)

    if compare_responses:
        parsed_operations = []

        for element in compare_responses:
            parsed_operations.append(
                list(map(lambda x: x, Parser(response.json(), element).do_parse().__dict__.values())))

        google_sheet.add_a_new_entry(parsed_operations, compare_responses)

    return {
        'statusCode': 200
    }


if __name__ == '__main__':
    logger.is_running()
    main()
    logger.is_stopped()
