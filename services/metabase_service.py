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


async def consultar_hubspot_general(codigo_bia: str) -> dict:
    """
    Consulta la tabla Hubspot General (src-tbl 19438) por código Bia.

    Descubre IDs de campos dinámicamente vía /api/table/{id}/query_metadata, así
    no hace falta saber el nombre SQL exacto de cada columna. Devuelve un dict
    con razón social, dirección, ciudad y energía (kWh).
    """
    import os
    import unicodedata

    def _norm(s: str) -> str:
        """Normaliza para comparar: minúsculas + sin acentos + sin espacios redundantes."""
        s = unicodedata.normalize("NFD", s or "")
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return " ".join(s.lower().split())

    table_id = os.getenv("HUBSPOT_GENERAL_TABLE_ID", "19438")
    headers  = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        meta = await client.get(
            f"{METABASE_URL}/api/table/{table_id}/query_metadata",
            headers=headers,
        )
        meta.raise_for_status()
        meta_json = meta.json()

        # display_name normalizado -> field_id (tolera "Dirección" vs "Direccion")
        fields_by_norm = {_norm(f["display_name"]): f["id"] for f in meta_json["fields"]}

        def find_field(*candidates):
            for c in candidates:
                fid = fields_by_norm.get(_norm(c))
                if fid:
                    return fid
            return None

        codigo_fid    = find_field("Codigo Bia")
        razon_fid     = find_field("Razon Social de la Empresa")
        direccion_fid = find_field("Direccion de la Frontera")
        ciudad_fid    = find_field("Ciudad")
        energia_fid   = find_field("Energia")

        if not codigo_fid:
            disponibles = sorted(f["display_name"] for f in meta_json["fields"])
            raise ValueError(
                f"No encuentro la columna del Código Bia en Hubspot General. "
                f"Columnas disponibles: {disponibles[:30]}..."
            )

        body = {
            "database": 21,
            "type": "query",
            "query": {
                "source-table": int(table_id),
                "filter": ["=", ["field", codigo_fid, None], codigo_bia],
                "limit": 1,
            },
        }
        r = await client.post(f"{METABASE_URL}/api/dataset", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    rows = data["data"]["rows"]
    cols = [c["display_name"] for c in data["data"]["cols"]]
    if not rows:
        raise ValueError(f"No se encontró cuenta con Código Bia '{codigo_bia}' en Hubspot General")

    record = dict(zip(cols, rows[0]))

    def get_by_fid(fid):
        if not fid:
            return ""
        # Find column index by field id from cols metadata
        for idx, col in enumerate(data["data"]["cols"]):
            if col.get("id") == fid:
                return rows[0][idx]
        return ""

    return {
        "codigo_bia":   codigo_bia,
        "razon_social": str(get_by_fid(razon_fid) or "").strip(),
        "direccion":    str(get_by_fid(direccion_fid) or "").strip(),
        "ciudad":       str(get_by_fid(ciudad_fid) or "").strip(),
        "energia":      float(get_by_fid(energia_fid) or 0),
    }


# ---------------------------------------------------------------------------
# ESSA — consultas por contract_id en Hubspot General + Alcances General
# ---------------------------------------------------------------------------
import unicodedata


def _norm(s: str) -> str:
    """Normaliza un string para comparación: minúsculas, sin acentos, sin
    espacios redundantes. Tolera 'Razón Social' vs 'Razon Social'."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


async def _consultar_por_contract_id(table_id: int, contract_id: str) -> dict:
    """Helper: consulta una tabla de Metabase filtrando por contract_id y
    devuelve la primera fila como dict {display_name -> valor}.

    Descubre el field_id de la columna contract_id dinámicamente vía
    `query_metadata` (acepta variantes 'Contract Id', 'Contract ID', 'Contract_id').
    Lanza ValueError si la columna no existe o si no hay registros.
    """
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30) as client:
        meta = await client.get(
            f"{METABASE_URL}/api/table/{table_id}/query_metadata",
            headers=headers,
        )
        meta.raise_for_status()
        meta_json = meta.json()

        fields_by_norm = {_norm(f["display_name"]): f for f in meta_json["fields"]}

        cid_field = None
        for cand in ("Contract Id", "Contract ID", "Contract_Id", "ID Contrato",
                     "Contract", "Id Contrato"):
            f = fields_by_norm.get(_norm(cand))
            if f:
                cid_field = f
                break
        if not cid_field:
            disponibles = sorted(f["display_name"] for f in meta_json["fields"])
            raise ValueError(
                f"No encuentro la columna 'Contract ID' en table {table_id}. "
                f"Columnas disponibles: {disponibles[:30]}..."
            )

        base_type = cid_field.get("base_type", "")
        valor_filtro: int | str = (
            int(contract_id) if "Integer" in base_type or "Number" in base_type
            else contract_id
        )

        body = {
            "database": 21,
            "type": "query",
            "query": {
                "source-table": int(table_id),
                "filter": ["=", ["field", cid_field["id"], None], valor_filtro],
                "limit": 1,
            },
        }
        r = await client.post(f"{METABASE_URL}/api/dataset", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    rows = data["data"]["rows"]
    if not rows:
        raise ValueError(
            f"No se encontró registro con contract_id={contract_id} en table {table_id}"
        )
    cols = [c["display_name"] for c in data["data"]["cols"]]
    return dict(zip(cols, rows[0]))


def _get(record: dict, *candidates: str) -> str:
    """Busca un campo en `record` tolerando variantes de acento/mayúscula."""
    for c in candidates:
        n_target = _norm(c)
        for k, v in record.items():
            if _norm(k) == n_target:
                return "" if v is None else str(v).strip()
    return ""


async def consultar_essa_hubspot_general(contract_id: str) -> dict:
    """Consulta Hubspot General (table 19438) por contract_id y devuelve los
    campos que necesitamos para el formato ESSA (Sec II, III, IV) y para la
    solicitud de retiro de sellos (Titulo)."""
    record = await _consultar_por_contract_id(19438, contract_id)
    return {
        "razon_social":       _get(record, "Razon Social de la Empresa"),
        "nit":                _get(record, "Numero de documento del amepresa",
                                          "Numero de documento de la empresa",
                                          "Numero de documento empresa"),
        "nic":                _get(record, "Nic"),
        "ciudad":             _get(record, "Ciudad"),
        "departamento":       _get(record, "Departamento"),
        "direccion_frontera": _get(record, "Direccion de la Frontera"),
        "codigo_ciiu":        _get(record, "Codigo Ciiu"),
        "titulo":             _get(record, "Titulo", "Título"),
    }


async def consultar_alcances_general(contract_id: str) -> dict:
    """Consulta Alcances General (table 19439) por contract_id y devuelve los
    campos que necesitamos para la Sec VII (Observaciones)."""
    record = await _consultar_por_contract_id(19439, contract_id)
    return {
        # Nota: el nombre real en Metabase es "Tipo de Medida Encontrado" (masc),
        # incluimos ambas variantes por si cambia.
        "tipo_medida":        _get(record, "Tipo de Medida Encontrado",
                                           "Tipo de Medida Encontrada"),
        "maniobra":           _get(record, "Maniobra"),
        "tiempo_corte_h":     _get(record, "Tiempo de Corte H"),
        "requiere_descargos": _get(record, "Requiere Descargos Del Or",
                                           "Requiere descargos del OR"),
    }


# ---------------------------------------------------------------------------
# Kick-off — consulta por Razón Social en Hubspot General
# ---------------------------------------------------------------------------
async def consultar_kickoff_cuentas_por_razon_social(razon_social: str) -> list[dict]:
    """Devuelve TODAS las cuentas de una Razón Social en Hubspot General
    (table 19438), cada una como dict con contract_id, nic, ciudad,
    departamento y operador_red.

    Una misma razón social tiene normalmente varias cuentas (varios
    contract_id). Lanza ValueError si no encuentra ninguna.
    """
    headers = {"X-API-KEY": METABASE_API_KEY, "Content-Type": "application/json"}
    table_id = int(os.getenv("HUBSPOT_GENERAL_TABLE_ID", "19438"))

    async with httpx.AsyncClient(timeout=30) as client:
        meta = await client.get(
            f"{METABASE_URL}/api/table/{table_id}/query_metadata",
            headers=headers,
        )
        meta.raise_for_status()
        fields = meta.json()["fields"]
        fields_by_norm = {_norm(f["display_name"]): f for f in fields}

        razon_f = fields_by_norm.get(_norm("Razon Social de la Empresa"))
        if not razon_f:
            raise ValueError(
                f"No encuentro la columna 'Razon Social de la Empresa' en table {table_id}."
            )

        body = {
            "database": 21,
            "type": "query",
            "query": {
                "source-table": table_id,
                "filter": ["=", ["field", razon_f["id"], None], razon_social],
                "limit": 2000,
            },
        }
        r = await client.post(f"{METABASE_URL}/api/dataset", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    rows = data["data"]["rows"]
    if not rows:
        raise ValueError(
            f"No se encontró ninguna cuenta con Razón Social '{razon_social}' "
            f"en Hubspot General."
        )

    cols = [c["display_name"] for c in data["data"]["cols"]]
    cuentas = []
    for row in rows:
        rec = dict(zip(cols, row))
        cuentas.append({
            "contract_id":  _get(rec, "Contract ID", "Contract Id"),
            "codigo_bia":   _get(rec, "Codigo Bia", "Código Bia"),
            "nic":          _get(rec, "Nic"),
            "ciudad":       _get(rec, "Ciudad"),
            "departamento": _get(rec, "Departamento"),
            "direccion":    _get(rec, "Direccion De La Frontera",
                                       "Dirección de la Frontera"),
            "operador_red": _get(rec, "Operador De Red", "Operador de Red"),
        })
    return cuentas


async def consultar_kickoff_ors_por_razon_social(razon_social: str) -> list[str]:
    """Devuelve los Operadores de Red distintos para una Razón Social
    (azúcar sintáctico sobre `consultar_kickoff_cuentas_por_razon_social`)."""
    cuentas = await consultar_kickoff_cuentas_por_razon_social(razon_social)
    return sorted({c["operador_red"] for c in cuentas if c["operador_red"]})


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
