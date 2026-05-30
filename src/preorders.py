from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any
from uuid import uuid4


class PreOrderStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


@dataclass
class PreOrder:
    customer_name: str
    contact: str
    product_description: str
    weight_oz: float
    deposit_usd: float
    id: str = field(default_factory=lambda: str(uuid4()))
    status: PreOrderStatus = PreOrderStatus.PENDING
    created_date: date = field(default_factory=date.today)
    inventory_item_id: str | None = None
    forecast_delivery_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "contact": self.contact,
            "product_description": self.product_description,
            "weight_oz": self.weight_oz,
            "deposit_usd": self.deposit_usd,
            "status": self.status.value,
            "created_date": self.created_date.isoformat(),
            "inventory_item_id": self.inventory_item_id,
            "forecast_delivery_date": (
                self.forecast_delivery_date.isoformat()
                if self.forecast_delivery_date
                else None
            ),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PreOrder:
        return cls(
            id=d["id"],
            customer_name=d["customer_name"],
            contact=d["contact"],
            product_description=d["product_description"],
            weight_oz=d["weight_oz"],
            deposit_usd=d["deposit_usd"],
            status=PreOrderStatus(d["status"]),
            created_date=date.fromisoformat(d["created_date"]),
            inventory_item_id=d.get("inventory_item_id"),
            forecast_delivery_date=(
                date.fromisoformat(d["forecast_delivery_date"])
                if d.get("forecast_delivery_date")
                else None
            ),
        )


class PreOrderLedger:
    def __init__(self) -> None:
        self._items: list[PreOrder] = []
        self._index: dict[str, PreOrder] = {}

    def add(self, order: PreOrder) -> None:
        if order.id in self._index:
            raise ValueError(f"PreOrder with id {order.id!r} already exists in the ledger.")
        self._items.append(order)
        self._index[order.id] = order

    def get(self, order_id: str) -> PreOrder:
        if order_id not in self._index:
            raise KeyError(order_id)
        return self._index[order_id]

    def list(self) -> list[PreOrder]:
        return list(self._items)

    def fulfill(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status != PreOrderStatus.PENDING:
            raise ValueError(
                f"Cannot transition from {order.status.value!r} to 'fulfilled'. "
                "Only pending orders can be fulfilled."
            )
        order.status = PreOrderStatus.FULFILLED

    def cancel(self, order_id: str) -> None:
        order = self.get(order_id)
        if order.status == PreOrderStatus.FULFILLED:
            raise ValueError(
                "Cannot transition from 'fulfilled' to 'cancelled'."
            )
        order.status = PreOrderStatus.CANCELLED
