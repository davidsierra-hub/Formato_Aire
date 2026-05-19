import httpx
import os

METABASE_URL = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")


async def consultar_wms_por_seriales(seriales: list) -> dict:
    """Query WMS General (table 19471) by serial list. Returns dict keyed by serial."""
    url = f"{METABASE_URL}/api/dataset"
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}
    body = {
        "database": 21,
        "type": "query",
        "query": {
            "source-table": 19471,
            "filter": [
                "in",
                ["field", "serial", {"base-type": "type/Text"}],
                seriales,
            ],
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    cols = [c["name"] for c in data["data"]["cols"]]
    rows = [dict(zip(cols, row)) for row in data["data"]["rows"]]

    resultado = {}
    for row in rows:
        serial = row.get("serial")
        if serial and serial not in resultado:
            resultado[serial] = row
    return resultado
