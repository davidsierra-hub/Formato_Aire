import httpx
import os
import re

METABASE_URL     = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")


async def consultar_alcances(contract_id: str) -> dict | None:
    """
    Consulta la tabla Alcances General (19439) filtrando por contract_id.
    Retorna la primera fila como dict, o None si no hay datos.
    """
    url = f"{METABASE_URL}/api/dataset"
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}
    body = {
        "database": 21,
        "type": "query",
        "query": {
            "source-table": 19439,
            "filter": ["=", ["field", 174175, None], str(contract_id)],
            "limit": 1,
        }
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    rows = data["data"]["rows"]
    if not rows:
        return None
    cols = [c["name"] for c in data["data"]["cols"]]
    return dict(zip(cols, rows[0]))


def extraer_folder_id(url: str) -> str | None:
    """Extrae el folder ID de una URL de Google Drive."""
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url or "")
    return match.group(1) if match else None
