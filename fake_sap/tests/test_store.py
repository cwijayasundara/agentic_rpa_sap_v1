from fake_sap.store import Store
from fake_sap.seed import seed_store


def test_seed_loads_master_data():
    store = Store()
    seed_store(store)
    assert store.customers["1000002"].credit_ok is False
    assert store.materials["MZ-FG-OOS"].stock == 3
    assert store.materials["MZ-FG-NP"].pricing_condition_exists is False


def test_number_ranges_are_deterministic():
    store = Store()
    seed_store(store)
    assert store.next_sales_order() == "4500000000"
    assert store.next_sales_order() == "4500000001"
    assert store.next_delivery() == "8000000000"
    assert store.next_billing() == "9000000000"
