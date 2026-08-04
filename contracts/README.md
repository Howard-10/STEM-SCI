# Contracts

`openapi/` contains the exported FastAPI contract for both the Context MVP and the Controller workflow API. `schemas/` is reserved for shared, versioned data-contract schemas.

The OpenAPI file is generated with `backend/scripts/export_openapi.py` after backend API changes. It is a transport contract; internal Pydantic domain models remain under `backend/src/stem_sci/`.
