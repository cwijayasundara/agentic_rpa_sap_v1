from fake_sap.store import Store, Customer, Material


def seed_store(store: Store) -> None:
    store.customers.clear()
    store.materials.clear()
    store.sales_orders.clear()
    store.deliveries.clear()
    store.billing_documents.clear()
    store._so_counter = 4500000000
    store._dlv_counter = 8000000000
    store._bill_counter = 9000000000

    for c in [
        Customer("1000001", "Acme Manufacturing", True),
        Customer("1000002", "Globex Industrial", False),
    ]:
        store.customers[c.customer] = c

    for m in [
        Material("MZ-FG-C100", "Pump C100", 100, 50.0, True),
        Material("MZ-FG-OOS", "Valve OOS", 3, 30.0, True),
        Material("MZ-FG-NP", "Gasket NP", 100, 25.0, False),
    ]:
        store.materials[m.material] = m
