import httpx
import os

METABASE_URL     = os.getenv("METABASE_URL")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")

SQL_QUERY = """
SELECT
    p.contract_id,
    me.meter_id                  AS nic,
    me.sic_id                    AS sic,
    dc_c.business_name           AS razon_social_de_la_empresa,
    me.metering_connection       AS tipo_de_medida,
    me.grid_operator             AS operador_red,
    me.current_provider          AS comercializador_anterior,
    me.address                   AS direccion_de_la_frontera,
    me.state                     AS departamento,
    me.city                      AS ciudad,
    s.name                       AS sku,
    s.category                   AS categoria,
    i.serial,
    i.brand                      AS marca

FROM hubspot_etl.project p
    LEFT JOIN hubspot_etl.meters_to_project mtp ON p.hs_object_id = mtp.project_id        AND mtp.type_id = '51'
    LEFT JOIN hubspot_etl.meters me             ON mtp.meters_id = me.hs_object_id
    LEFT JOIN hubspot_etl.deal_to_meters dtm    ON mtp.meters_id = dtm.meters_id           AND dtm.type_id = '43'
    LEFT JOIN hubspot_etl.deal d                ON dtm.deal_id = d.hs_object_id            AND d.fivetran_deleted = false
    LEFT JOIN hubspot_etl.company_deal dc       ON d.hs_object_id = dc.deal_id             AND dc.type_id = '5'
    LEFT JOIN hubspot_etl.company dc_c          ON dc.company_id = dc_c.hs_object_id       AND dc_c.fivetran_deleted = false
    LEFT JOIN ops_wms.requirement_group rq      ON rq.contract_id = p.contract_id
    LEFT JOIN ops_wms.requirements r            ON r.requirement_group_id = rq.id
    LEFT JOIN ops_wms.inventory i               ON r.id = i.requirement_id
    LEFT JOIN ops_wms.sku s                     ON i.sku_id = s.id

WHERE p.contract_id = {contract_id}
    AND s.category IN ('Medidor', 'Transformador de corriente', 'Transformador de potencial')
    AND i.id IS NOT NULL
"""


async def consultar_metabase(contract_id: str) -> list:
    url = f"{METABASE_URL}/api/dataset"
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}
    body = {
        "database": 21,
        "type": "native",
        "native": {"query": SQL_QUERY.replace("{contract_id}", contract_id)}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    rows = data["data"]["rows"]
    cols = [c["name"] for c in data["data"]["cols"]]
    return [dict(zip(cols, row)) for row in rows]


def parsear_datos(records: list) -> dict:
    if not records:
        raise ValueError("No se encontraron datos para este contract_id")
    base = records[0]
    equipos = [
        {
            "sku":      r.get("sku") or "",
            "categoria": r.get("categoria") or "",
            "serial":   r.get("serial") or "",
            "marca":    r.get("marca") or "",
        }
        for r in records if r.get("sku")
    ]
    return {
        "contract_id": str(base.get("contract_id", "")),
        "nic":          str(base.get("nic", "")),
        "razon_social": str(base.get("razon_social_de_la_empresa", "")),
        "tipo_medida":  str(base.get("tipo_de_medida", "")),
        "direccion":    str(base.get("direccion_de_la_frontera", "")),
        "departamento": str(base.get("departamento", "")),
        "ciudad":       str(base.get("ciudad", "")),
        "equipos":      equipos,
    }
