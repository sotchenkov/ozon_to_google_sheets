import logging
import os


logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = logging.getLogger().handlers[0]
formatter = logging.Formatter('[%(levelname)s]\t%(message)s\n')

handler.setFormatter(formatter)

logger.addHandler(handler)



def is_running():
    logger.info("The application has been started")


def check_request(url: str, response_status: int, info=None):
    if response_status == 200:
        logger.info(f'Success request to {url}')
    else:
        logger.error(f'Request to {url} failed with info: {info}')


def check_file_exists(path: str):
    if os.path.exists(path):
        logger.info(f'File {path} received')
    else:
        logger.error(f'File {path} does not exist')


def check_new_orders(elements: list):
    if not elements:
        logger.info("There have been no new operations in the last hour")
    else:
        logger.info(f"You have {len(elements)} new operations")


def is_parsed(element_id: int):
    logger.info(f'Operation with id {element_id} successfully parsed')


def is_not_parsed(element_id: int):
    logger.error(f'Could not parse operation with id {element_id}', exc_info=True)


def unknown_marketplace_service_name(name: str):
    logger.warning(f'Unknown marketplace service name "{name}"')


def is_connected_to_google_sheets():
    logger.info('Success connecting to google sheets')


def connection_error_to_google_sheets():
    logger.error('Connection error to google sheets', exc_info=True)


def is_added_to_google_sheets(operation_ids: list):
    for operation in operation_ids:
        logger.info(f'Operation {operation} added to google tables')


def error_adding_to_google_sheets(operation_ids: list):
    for operation in operation_ids:
        logger.error(f'Could not send an update request to google sheets for operation {operation}', exc_info=True)


def is_stopped():
    logger.info('The application has shut down')
