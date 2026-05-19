import httpx
import os

METABASE_URL = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")


async def consultar_wms_por_seriales(seriales: list) -> dict:
    """
    Query WMS General (table 19471) by serial list.
    WMS stores serials with a leading zero (e.g. '037299684961') while
    users enter them without it ('37299684961'), so we query both forms.
    Returns dict keyed by the original user-entered serial.
    """
    url = f"{METABASE_URL}/api/dataset"
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}

    # Build lookup: wms_serial -> user_serial (to remap results back)
    serial_map = {}
    for s in seriales:
        serial_map[s] = s
        padded = "0" + s
        serial_map[padded] = s

    wms_seriales = list(serial_map.keys())

    # MBQL "IN" uses ["=", field, v1, v2, ...]
    body = {
        "database": 21,
        "type": "query",
        "query": {
            "source-table": 19471,
            "filter": ["=", ["field", "serial", {"base-type": "type/Text"}]] + wms_seriales,
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
        wms_serial = row.get("serial")
        if not wms_serial:
            continue
        user_serial = serial_map.get(wms_serial)
        if user_serial and user_serial not in resultado:
            resultado[user_serial] = row
    return resultado
