import xml.etree.ElementTree as ET
from fake_sap import metadata, schema


def test_render_is_well_formed_xml():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    # parses without error
    ET.fromstring(xml)
    assert xml.startswith("<?xml")


def test_render_declares_entity_types_keys_and_sets():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    assert 'EntityType Name="A_SalesOrderType"' in xml
    assert '<PropertyRef Name="SalesOrder"/>' in xml
    assert 'Property Name="TotalCreditCheckStatus" Type="Edm.String" MaxLength="1"' in xml
    assert 'EntitySet Name="A_SalesOrder" EntityType="API_SALES_ORDER_SRV.A_SalesOrderType"' in xml


def test_decimal_property_has_no_maxlength():
    xml = metadata.render_metadata(schema.SALES_ORDER_SERVICE)
    assert '<Property Name="TotalNetAmount" Type="Edm.Decimal" Nullable="true"/>' in xml


from starlette.testclient import TestClient
from fake_sap.app import create_app

SO = "/sap/opu/odata/sap/API_SALES_ORDER_SRV"
DLV = "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV"
BILL = "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV"


def test_metadata_endpoints_served_for_three_services():
    client = TestClient(create_app())
    for base, marker in [
        (SO, 'Name="A_SalesOrderType"'),
        (DLV, 'Name="A_OutbDeliveryHeaderType"'),
        (BILL, 'Name="A_BillingDocumentType"'),
    ]:
        r = client.get(f"{base}/$metadata")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/xml")
        assert marker in r.text
