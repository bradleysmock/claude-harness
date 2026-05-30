from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.preorders import PreOrder, PreOrderLedger, PreOrderStatus


# ── PreOrder dataclass ────────────────────────────────────────────────────────


def test_preorder_defaults():
    o = PreOrder(
        customer_name="Alice",
        contact="alice@example.com",
        product_description="Merino yarn, 8oz",
        weight_oz=8.0,
        deposit_usd=20.0,
    )
    assert o.id  # uuid assigned
    assert o.status == PreOrderStatus.PENDING
    assert o.created_date == date.today()
    assert o.inventory_item_id is None
    assert o.forecast_delivery_date is None


def test_preorder_to_dict_round_trip():
    o = PreOrder(
        customer_name="Bob",
        contact="bob@example.com",
        product_description="Roving",
        weight_oz=4.0,
        deposit_usd=10.0,
        forecast_delivery_date=date(2026, 9, 1),
    )
    d = o.to_dict()
    restored = PreOrder.from_dict(d)
    assert restored.id == o.id
    assert restored.customer_name == o.customer_name
    assert restored.contact == o.contact
    assert restored.product_description == o.product_description
    assert restored.weight_oz == pytest.approx(o.weight_oz)
    assert restored.deposit_usd == pytest.approx(o.deposit_usd)
    assert restored.status == o.status
    assert restored.created_date == o.created_date
    assert restored.forecast_delivery_date == o.forecast_delivery_date


def test_preorder_to_dict_serializes_dates_as_strings():
    o = PreOrder(
        customer_name="Carol",
        contact="c@c.com",
        product_description="x",
        weight_oz=1.0,
        deposit_usd=5.0,
        forecast_delivery_date=date(2026, 10, 15),
    )
    d = o.to_dict()
    assert isinstance(d["created_date"], str)
    assert isinstance(d["forecast_delivery_date"], str)
    assert d["status"] == "pending"


def test_preorder_from_dict_null_optional_fields():
    d = {
        "id": "abc",
        "customer_name": "Dan",
        "contact": "d@d.com",
        "product_description": "y",
        "weight_oz": 2.0,
        "deposit_usd": 8.0,
        "status": "pending",
        "created_date": "2026-05-30",
        "inventory_item_id": None,
        "forecast_delivery_date": None,
    }
    o = PreOrder.from_dict(d)
    assert o.inventory_item_id is None
    assert o.forecast_delivery_date is None


# ── PreOrderLedger ────────────────────────────────────────────────────────────


def _make_order(**kwargs) -> PreOrder:
    defaults = dict(
        customer_name="Test",
        contact="t@t.com",
        product_description="Yarn",
        weight_oz=4.0,
        deposit_usd=15.0,
    )
    defaults.update(kwargs)
    return PreOrder(**defaults)


def test_ledger_add_and_get():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    assert ledger.get(o.id) is o


def test_ledger_add_duplicate_raises():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    with pytest.raises(ValueError, match="already exists"):
        ledger.add(o)


def test_ledger_get_unknown_raises():
    ledger = PreOrderLedger()
    with pytest.raises(KeyError):
        ledger.get("no-such-id")


def test_ledger_list_returns_copy():
    ledger = PreOrderLedger()
    o1 = _make_order()
    o2 = _make_order()
    ledger.add(o1)
    ledger.add(o2)
    items = ledger.list()
    assert len(items) == 2
    items.clear()
    assert len(ledger.list()) == 2  # original unaffected


def test_ledger_fulfill_pending_order():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    ledger.fulfill(o.id)
    assert ledger.get(o.id).status == PreOrderStatus.FULFILLED


def test_ledger_fulfill_already_fulfilled_raises():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    ledger.fulfill(o.id)
    with pytest.raises(ValueError):
        ledger.fulfill(o.id)


def test_ledger_cancel_pending_order():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    ledger.cancel(o.id)
    assert ledger.get(o.id).status == PreOrderStatus.CANCELLED


def test_ledger_cancel_fulfilled_raises():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    ledger.fulfill(o.id)
    with pytest.raises(ValueError):
        ledger.cancel(o.id)


def test_ledger_cancel_already_cancelled_does_not_raise():
    ledger = PreOrderLedger()
    o = _make_order()
    ledger.add(o)
    ledger.cancel(o.id)
    # Cancelling an already-cancelled order is idempotent (not fulfilled, so no error)
    ledger.cancel(o.id)
    assert ledger.get(o.id).status == PreOrderStatus.CANCELLED


# ── FarmStore integration ─────────────────────────────────────────────────────


def test_farmstore_round_trip(tmp_path: Path):
    from flock import FarmStore

    store = FarmStore(tmp_path / "farm.json")
    ledger = PreOrderLedger()
    o = PreOrder(
        customer_name="Eve",
        contact="e@e.com",
        product_description="Roving, 6oz",
        weight_oz=6.0,
        deposit_usd=25.0,
        forecast_delivery_date=date(2026, 11, 1),
    )
    ledger.add(o)
    store.save_preorders(ledger)

    loaded = store.load_preorders()
    assert len(loaded.list()) == 1
    restored = loaded.get(o.id)
    assert restored.customer_name == "Eve"
    assert restored.forecast_delivery_date == date(2026, 11, 1)
    assert restored.status == PreOrderStatus.PENDING


def test_farmstore_load_missing_key_returns_empty(tmp_path: Path):
    from flock import FarmStore

    store = FarmStore(tmp_path / "farm.json")
    # Write a JSON file with no "preorders" key
    (tmp_path / "farm.json").write_text(json.dumps({"animals": []}))
    ledger = store.load_preorders()
    assert ledger.list() == []


def test_farmstore_load_nonexistent_file_returns_empty(tmp_path: Path):
    from flock import FarmStore

    store = FarmStore(tmp_path / "farm.json")
    ledger = store.load_preorders()
    assert ledger.list() == []


def test_farmstore_save_preserves_existing_keys(tmp_path: Path):
    from flock import FarmStore

    path = tmp_path / "farm.json"
    path.write_text(json.dumps({"animals": [{"id": "a1", "name": "Clover"}]}))

    store = FarmStore(path)
    ledger = PreOrderLedger()
    ledger.add(_make_order())
    store.save_preorders(ledger)

    data = json.loads(path.read_text())
    assert "animals" in data
    assert len(data["preorders"]) == 1
