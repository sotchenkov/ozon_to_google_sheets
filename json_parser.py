import json

from data.table import Table
from logs import logger


class Parser:
    def __init__(self, response, new_elements):
        self.response = response
        self.new_elements = new_elements
        self.table = Table()

    def do_parse(self) -> Table:
        for operations in self.response['result']['operations']:
            if operations['operation_id'] == self.new_elements:
                try:
                    self.parse_head(operations)
                    self.parse_item(operations)
                    self.parse_services(operations)

                    logger.is_parsed(operations['operation_id'])

                    return self.table

                except RuntimeError:
                    logger.is_not_parsed(operations['operation_id'])

    def parse_head(self, obj: json) -> None:
        self.table.operation_date = obj['operation_date'][:10]
        self.table.operation_type_name = obj['operation_type_name']
        self.table.operation_id = obj['operation_id']
        self.table.posting_number = obj['posting']['posting_number']
        self.table.delivery_schema = obj['posting']['delivery_schema']
        self.table.accruals_for_sale = obj['accruals_for_sale']
        self.table.sale_commission = obj['sale_commission']
        self.table.amount = obj['amount']

        self.table.order_date = obj['posting']['order_date'][:10] if \
            obj['posting']['order_date'] != "" else self.table.operation_date

        if self.table.accruals_for_sale != 0:
            self.table.sale_commission_percents = str(
                int(obj['sale_commission'] / self.table.accruals_for_sale * -100)) + '%'

    def parse_item(self, obj: json) -> None:
        if obj['items']:
            self.table.sku = obj['items'][0]['sku']
            self.table.name = obj['items'][0]['name']

    def parse_services(self, obj: json) -> None:
        for service in obj['services']:
            if service['name'] == 'MarketplaceServiceItemFulfillment':
                self.table.order_assembly = service['price']
            elif service['name'] == 'MarketplaceServiceItemDropoffPVZ' or 'MarketplaceServiceItemDropoffSC':
                self.table.shipment_processing = service['price']
            elif service['name'] == 'MarketplaceServiceItemDirectFlowTrans':
                self.table.highway = service['price']
            elif service['name'] == 'MarketplaceServiceItemDelivToCustomer':
                self.table.last_mile = service['price']
            elif service['name'] == 'MarketplaceServiceItemReturnFlowTrans':
                self.table.reverse_highway = service['price']
            elif service['name'] == 'MarketplaceServiceItemReturnAfterDelivToCustomer':
                self.table.refund_processing = service['price']
            elif service['name'] == 'MarketplaceServiceItemReturnNotDelivToCustomer':
                self.table.processing_of_cancelled_or_unclaimed_item = service['price']
            elif service['name'] == 'MarketplaceServiceItemReturnPartGoodsCustomer':
                self.table.processing_of_unbought_item = service['price']
            elif service['name'] == 'MarketplaceServiceItemDirectFlowLogistic':
                self.table.logistics = service['price']
            elif service['name'] == 'MarketplaceServiceItemReturnFlowLogistic':
                self.table.reverse_logistics = service['price']
            else:
                logger.unknown_marketplace_service_name(service['name'])
