import pytest
from fake_sap.store import Store
from fake_sap.seed import seed_store
from fake_sap import rules
from fake_sap.rules import SapError


@pytest.fixture
def store():
    s = Store()
    seed_store(s)
    return s


def test_price_item_with_condition(store):
    net, incomplete = rules.price_item(store, "MZ-FG-C100", 10)
    assert net == 500.0
    assert incomplete is False


def test_price_item_missing_condition_is_zero_and_incomplete(store):
    net, incomplete = rules.price_item(store, "MZ-FG-NP", 10)
    assert net == 0.0
    assert incomplete is True


def test_credit_block_flag(store):
    assert rules.is_credit_blocked(store, "1000002") is True
    assert rules.is_credit_blocked(store, "1000001") is False


def test_atp_insufficient_raises_with_available(store):
    with pytest.raises(SapError) as exc:
        rules.check_atp(store, "MZ-FG-OOS", 10)
    assert exc.value.code == "INSUFFICIENT_STOCK"
    assert exc.value.detail["available"] == 3


def test_atp_ok(store):
    rules.check_atp(store, "MZ-FG-C100", 10)  # no raise
