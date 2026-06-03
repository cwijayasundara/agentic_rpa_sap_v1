# Vendored SAP OData API specifications

These are official SAP S/4HANA Cloud OData v2 API definitions, used as the
**schema source of truth** for the Fake-SAP simulator's field names, types, and
status codes. They are referenced (not generated into runtime endpoints).

| File | SAP service | Source |
|---|---|---|
| `API_SALES_ORDER_SRV.json` | Sales Order (A2X) | SAP Business Accelerator Hub |
| `API_MATERIAL_DOCUMENT_SRV.json` | Material Documents – Read, Create | SAP Business Accelerator Hub |

Originally mirrored from the reference repo
<https://github.com/FelipeLujan/SAP-O2C-POC/tree/main/sap_api>.

`API_MATERIAL_DOCUMENT_SRV.json` is vendored for reference only; goods-movement
postings are not modelled against it (see the design doc).
