"""Typed domain models for Ozon finance accruals and sheet output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import astuple, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class OzonPayloadError(ValueError):
    """Raised when an Ozon response does not match the documented schema."""


@dataclass(frozen=True, slots=True)
class Money:
    """An exact monetary value returned by Ozon."""

    amount: Decimal = Decimal("0")
    currency: str = ""

    @classmethod
    def from_api(cls, value: object, path: str) -> Money:
        if value is None:
            return cls()
        data = _mapping(value, path)
        raw_amount = data.get("amount", "0")
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int, float)):
            raise OzonPayloadError(f"{path}.amount must be a decimal value")
        try:
            amount = Decimal(str(raw_amount))
        except InvalidOperation as error:
            raise OzonPayloadError(f"{path}.amount must be a decimal value") from error
        return cls(
            amount=amount,
            currency=_optional_string(data.get("currency"), f"{path}.currency"),
        )


@dataclass(frozen=True, slots=True)
class AccrualFee:
    """One service or fee identified by the accrual type catalogue."""

    type_id: int
    accrued: Money

    @classmethod
    def from_api(cls, value: object, path: str) -> AccrualFee:
        data = _mapping(value, path)
        return cls(
            type_id=_integer(data.get("type_id"), f"{path}.type_id"),
            accrued=Money.from_api(data.get("accrued"), f"{path}.accrued"),
        )


@dataclass(frozen=True, slots=True)
class Commission:
    commission: Money = Money()
    commission_ratio: str = ""
    sale_amount: Money = Money()
    sale_commission: Money = Money()
    sale_price: Money = Money()
    seller_price: Money = Money()
    bonus: Money = Money()
    coinvestment: Money = Money()

    @classmethod
    def from_api(cls, value: object, path: str) -> Commission:
        if value is None:
            return cls()
        data = _mapping(value, path)
        return cls(
            commission=Money.from_api(data.get("commission"), f"{path}.commission"),
            commission_ratio=_optional_string(
                data.get("commission_ratio"), f"{path}.commission_ratio"
            ),
            sale_amount=Money.from_api(data.get("sale_amount"), f"{path}.sale_amount"),
            sale_commission=Money.from_api(
                data.get("sale_commission"), f"{path}.sale_commission"
            ),
            sale_price=Money.from_api(data.get("sale_price"), f"{path}.sale_price"),
            seller_price=Money.from_api(data.get("seller_price"), f"{path}.seller_price"),
            bonus=Money.from_api(data.get("bonus"), f"{path}.bonus"),
            coinvestment=Money.from_api(data.get("coinvestment"), f"{path}.coinvestment"),
        )


@dataclass(frozen=True, slots=True)
class Delivery:
    services: tuple[AccrualFee, ...] = ()
    total_accrued: Money = Money()

    @classmethod
    def from_api(cls, value: object, path: str) -> Delivery:
        if value is None:
            return cls()
        data = _mapping(value, path)
        services = _sequence(data.get("services"), f"{path}.services")
        return cls(
            services=tuple(
                AccrualFee.from_api(service, f"{path}.services[{index}]")
                for index, service in enumerate(services)
            ),
            total_accrued=Money.from_api(
                data.get("total_accrued"), f"{path}.total_accrued"
            ),
        )


@dataclass(frozen=True, slots=True)
class PostingProduct:
    sku: int
    commission: Commission = Commission()
    delivery: Delivery = Delivery()

    @classmethod
    def from_api(cls, value: object, path: str) -> PostingProduct:
        data = _mapping(value, path)
        return cls(
            sku=_integer(data.get("sku"), f"{path}.sku"),
            commission=Commission.from_api(data.get("commission"), f"{path}.commission"),
            delivery=Delivery.from_api(data.get("delivery"), f"{path}.delivery"),
        )


@dataclass(frozen=True, slots=True)
class Posting:
    delivery_schema: str = ""
    delivery_speed: int = 0
    products: tuple[PostingProduct, ...] = ()

    @classmethod
    def from_api(cls, value: object, path: str) -> Posting:
        if value is None:
            return cls()
        data = _mapping(value, path)
        products = _sequence(data.get("products"), f"{path}.products")
        return cls(
            delivery_schema=_optional_string(
                data.get("delivery_schema"), f"{path}.delivery_schema"
            ),
            delivery_speed=_optional_integer(
                data.get("delivery_speed"), f"{path}.delivery_speed"
            ),
            products=tuple(
                PostingProduct.from_api(product, f"{path}.products[{index}]")
                for index, product in enumerate(products)
            ),
        )


@dataclass(frozen=True, slots=True)
class ItemFees:
    sku: int
    fees: tuple[AccrualFee, ...] = ()

    @classmethod
    def from_api(cls, value: object, path: str) -> ItemFees:
        data = _mapping(value, path)
        fees = _sequence(data.get("fees"), f"{path}.fees")
        return cls(
            sku=_integer(data.get("sku"), f"{path}.sku"),
            fees=tuple(
                AccrualFee.from_api(fee, f"{path}.fees[{index}]")
                for index, fee in enumerate(fees)
            ),
        )


@dataclass(frozen=True, slots=True)
class Accrual:
    """One finance accrual, retaining every documented fee and product."""

    accrual_id: int
    accrued_category: str
    date: str
    unit_number: str
    total_amount: Money
    posting: Posting = Posting()
    item_fees: tuple[ItemFees, ...] = ()
    non_item_fee: AccrualFee | None = None
    container_fees: tuple[AccrualFee, ...] = ()

    @classmethod
    def from_api(cls, value: object, path: str) -> Accrual:
        data = _mapping(value, path)
        item_fees_data = _mapping_or_empty(data.get("item_fees"), f"{path}.item_fees")
        item_fees = _sequence(item_fees_data.get("fees"), f"{path}.item_fees.fees")
        non_item_data = data.get("non_item_fee")
        return cls(
            accrual_id=_integer(data.get("accrual_id"), f"{path}.accrual_id"),
            accrued_category=_optional_string(
                data.get("accrued_category"), f"{path}.accrued_category"
            ),
            date=_required_string(data.get("date"), f"{path}.date"),
            unit_number=_optional_string(data.get("unit_number"), f"{path}.unit_number"),
            total_amount=Money.from_api(data.get("total_amount"), f"{path}.total_amount"),
            posting=Posting.from_api(data.get("posting"), f"{path}.posting"),
            item_fees=tuple(
                ItemFees.from_api(item_fee, f"{path}.item_fees.fees[{index}]")
                for index, item_fee in enumerate(item_fees)
            ),
            non_item_fee=(
                AccrualFee.from_api(non_item_data, f"{path}.non_item_fee")
                if non_item_data
                else None
            ),
            container_fees=_find_accrual_fees(
                data.get("container_fees"), f"{path}.container_fees"
            ),
        )


@dataclass(frozen=True, slots=True)
class AccrualPage:
    accruals: tuple[Accrual, ...]
    last_id: str

    @classmethod
    def from_api(cls, value: object) -> AccrualPage:
        data = _mapping(value, "response")
        accruals = _sequence(data.get("accruals"), "response.accruals")
        return cls(
            accruals=tuple(
                Accrual.from_api(accrual, f"response.accruals[{index}]")
                for index, accrual in enumerate(accruals)
            ),
            last_id=_optional_string(data.get("last_id"), "response.last_id"),
        )


@dataclass(frozen=True, slots=True)
class AccrualType:
    type_id: int
    name: str
    description: str = ""

    @classmethod
    def from_api(cls, value: object, path: str) -> AccrualType:
        data = _mapping(value, path)
        return cls(
            type_id=_integer(data.get("id"), f"{path}.id"),
            name=_required_string(data.get("name"), f"{path}.name"),
            description=_optional_string(data.get("description"), f"{path}.description"),
        )


@dataclass(frozen=True, slots=True)
class PostingAccrual:
    posting_number: str
    sku: int
    quantity: int
    type_id: int
    accrual_date: str
    accrued: Money
    seller_price: Money


def parse_accrual_types(value: object) -> tuple[AccrualType, ...]:
    data = _mapping(value, "response")
    items = _sequence(data.get("accrual_types"), "response.accrual_types")
    return tuple(
        AccrualType.from_api(item, f"response.accrual_types[{index}]")
        for index, item in enumerate(items)
    )


def parse_posting_accruals(value: object) -> tuple[PostingAccrual, ...]:
    data = _mapping(value, "response")
    postings = _sequence(data.get("posting_accruals"), "response.posting_accruals")
    parsed: list[PostingAccrual] = []
    for posting_index, posting_value in enumerate(postings):
        posting_path = f"response.posting_accruals[{posting_index}]"
        posting = _mapping(posting_value, posting_path)
        posting_number = _required_string(
            posting.get("posting_number"), f"{posting_path}.posting_number"
        )
        accruals = _sequence(posting.get("accruals"), f"{posting_path}.accruals")
        for accrual_index, accrual_value in enumerate(accruals):
            path = f"{posting_path}.accruals[{accrual_index}]"
            accrual = _mapping(accrual_value, path)
            parsed.append(
                PostingAccrual(
                    posting_number=posting_number,
                    sku=_integer(accrual.get("sku"), f"{path}.sku"),
                    quantity=_integer(accrual.get("quantity"), f"{path}.quantity"),
                    type_id=_integer(accrual.get("type_id"), f"{path}.type_id"),
                    accrual_date=_required_string(
                        accrual.get("accrual_date"), f"{path}.accrual_date"
                    ),
                    accrued=Money.from_api(accrual.get("accrued"), f"{path}.accrued"),
                    seller_price=Money.from_api(
                        accrual.get("seller_price"), f"{path}.seller_price"
                    ),
                )
            )
    return tuple(parsed)


@dataclass(slots=True)
class TransactionRow:
    """One Google Sheets row in the adapter's stable 23-column order."""

    operation_date: str = ""
    operation_type_name: str = ""
    operation_id: int = 0
    posting_number: str = ""
    order_date: str = ""
    delivery_schema: str = ""
    sku: int | None = None
    name: str = ""
    count: int = 0
    accruals_for_sale: Decimal = Decimal("0")
    sale_commission_percents: str = ""
    sale_commission: Decimal = Decimal("0")
    order_assembly: Decimal = Decimal("0")
    shipment_processing: Decimal = Decimal("0")
    highway: Decimal = Decimal("0")
    last_mile: Decimal = Decimal("0")
    reverse_highway: Decimal = Decimal("0")
    refund_processing: Decimal = Decimal("0")
    processing_of_cancelled_or_unclaimed_item: Decimal = Decimal("0")
    processing_of_unbought_item: Decimal = Decimal("0")
    logistics: Decimal = Decimal("0")
    reverse_logistics: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")

    def as_list(self) -> list[Any]:
        """Return JSON-compatible values in the worksheet's stable order."""

        return [float(value) if isinstance(value, Decimal) else value for value in astuple(self)]


def _find_accrual_fees(value: object, path: str) -> tuple[AccrualFee, ...]:
    """Extract typed fee entries from the newly introduced container fee block."""

    if value is None:
        return ()
    if isinstance(value, Mapping):
        if "type_id" in value and "accrued" in value:
            return (AccrualFee.from_api(value, path),)
        found: list[AccrualFee] = []
        for key in sorted(value):
            found.extend(_find_accrual_fees(value[key], f"{path}.{key}"))
        return tuple(found)
    if _is_sequence(value):
        found = []
        for index, item in enumerate(value):
            found.extend(_find_accrual_fees(item, f"{path}[{index}]"))
        return tuple(found)
    return ()


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OzonPayloadError(f"{path} must be an object")
    return value


def _mapping_or_empty(value: object, path: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    return _mapping(value, path)


def _sequence(value: object, path: str) -> Sequence[Any]:
    if value is None:
        return ()
    if not _is_sequence(value):
        raise OzonPayloadError(f"{path} must be an array")
    return value


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool):
        raise OzonPayloadError(f"{path} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    raise OzonPayloadError(f"{path} must be an integer")


def _optional_integer(value: object, path: str) -> int:
    return 0 if value is None else _integer(value, path)


def _required_string(value: object, path: str) -> str:
    result = _optional_string(value, path)
    if not result:
        raise OzonPayloadError(f"{path} must be a non-empty string")
    return result


def _optional_string(value: object, path: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise OzonPayloadError(f"{path} must be a string")
    return value
