import gspread

from logs import logger


class GSpread:
    def __init__(self, credentials: str, sheet_name: str):
        try:
            logger.check_file_exists(credentials)

            gc = gspread.service_account(credentials)
            sh = gc.open(sheet_name)
            self.worksheet = sh.sheet1

            logger.is_connected_to_google_sheets()

        except ConnectionError:
            logger.connection_error_to_google_sheets()

    def get_operations(self) -> list:
        return self.worksheet.col_values(3)[1:]

    def search_last_line(self) -> int:
        return len(self.worksheet.col_values(1)) + 1

    def add_a_new_entry(self, data: list, operation_ids: list):
        cells_count = self.search_last_line()
        try:
            self.worksheet.update(f'A{cells_count}:W{cells_count + len(data)}', data, value_input_option='USER_ENTERED')

            logger.is_added_to_google_sheets(operation_ids)

        except RuntimeError:
            logger.error_adding_to_google_sheets(operation_ids)
