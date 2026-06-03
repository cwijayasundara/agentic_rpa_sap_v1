from __future__ import annotations
from fake_sap.schema import EntityType, Service

_EDMX_OPEN = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<edmx:Edmx Version="1.0" '
    'xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">\n'
    ' <edmx:DataServices '
    'xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
    'm:DataServiceVersion="2.0">\n'
)
_EDMX_CLOSE = " </edmx:DataServices>\n</edmx:Edmx>\n"


def _property_xml(prop) -> str:
    attrs = f'Name="{prop.name}" Type="{prop.edm_type}"'
    if prop.max_length is not None:
        attrs += f' MaxLength="{prop.max_length}"'
    attrs += ' Nullable="false"' if prop.is_key else ' Nullable="true"'
    return f"      <Property {attrs}/>"


def _entity_type_xml(et: EntityType) -> str:
    keys = [p for p in et.properties if p.is_key]
    key_refs = "".join(f'<PropertyRef Name="{p.name}"/>' for p in keys)
    props = "\n".join(_property_xml(p) for p in et.properties)
    return (
        f'    <EntityType Name="{et.name}Type">\n'
        f"      <Key>{key_refs}</Key>\n"
        f"{props}\n"
        f"    </EntityType>"
    )


def render_metadata(service: Service) -> str:
    ns = service.namespace
    types = "\n".join(_entity_type_xml(et) for _, et in service.entity_sets)
    sets = "\n".join(
        f'      <EntitySet Name="{name}" '
        f'EntityType="{ns}.{et.name}Type"/>'
        for name, et in service.entity_sets
    )
    schema_xml = (
        f'  <Schema Namespace="{ns}" '
        'xmlns="http://schemas.microsoft.com/ado/2008/09/edm">\n'
        f"{types}\n"
        f'    <EntityContainer Name="{ns}_Entities" '
        'm:IsDefaultEntityContainer="true">\n'
        f"{sets}\n"
        "    </EntityContainer>\n"
        "  </Schema>\n"
    )
    return _EDMX_OPEN + schema_xml + _EDMX_CLOSE
