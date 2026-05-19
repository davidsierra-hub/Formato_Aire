import httpx
import os

METABASE_URL     = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")

TIPO_MEDIDOR = "medidor"
TIPO_TC      = "transformador de corriente"
TIPO_TP      = "transformador de potencial"


async def consultar_wms(contract_id: str) -> dict:
    """
    Consulta la tabla Wms General filtrando por contract_id y
    tipo_sku en Medidor / Transformador de corriente / Transformador de potencial.
    Retorna un dict con claves 'medidor', 'tcs', 'tps', cada una lista de equipos.
    """
    url = f"{METABASE_URL}/api/dataset"
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}
    body = {
        "database": 21,
        "type": "query",
        "query": {
            "source-table": 19471,
            "filter": [
                "and",
                ["=", ["field", "contract_id", {"base-type": "type/Integer"}], int(contract_id)],
                ["starts-with",
                    ["field", "tipo_sku", {"base-type": "type/Text"}],
                    "T",
                    {"case-sensitive": False}
                ]
            ]
        }
    }

    # Primero traemos todos los equipos del contrato sin filtro de tipo
    body_all = {
        "database": 21,
        "type": "query",
        "query": {
            "source-table": 19471,
            "filter": ["=", ["field", "contract_id", {"base-type": "type/Integer"}], int(contract_id)]
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body_all, headers=headers)
        r.raise_for_status()
        data = r.json()

    cols = [c["name"] for c in data["data"]["cols"]]
    rows = [dict(zip(cols, row)) for row in data["data"]["rows"]]

    medidores = [r for r in rows if TIPO_MEDIDOR in (r.get("tipo_sku") or "").lower()]
    tcs       = [r for r in rows if TIPO_TC      in (r.get("tipo_sku") or "").lower()]
    tps       = [r for r in rows if TIPO_TP      in (r.get("tipo_sku") or "").lower()]

    return {"medidores": medidores, "tcs": tcs, "tps": tps}


async def descargar_pdf(url: str) -> bytes:
    """Descarga un PDF desde una URL y retorna los bytes."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content
