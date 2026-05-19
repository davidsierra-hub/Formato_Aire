import os
from services.drive_service import get_sheets_service

TELEMEDIDA_SHEET_ID = os.getenv("TELEMEDIDA_SHEET_ID")


def obtener_ips_disponibles(cantidad: int) -> list:
    """
    Reads BD_Telemedida sheet "Líneas".
    Filters rows where APN = bia.claro.com.co and Cod. Interno BIA = Disponible.
    Returns up to `cantidad` unique IP addresses.
    """
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=TELEMEDIDA_SHEET_ID,
        range="Líneas!A:H",
    ).execute()

    rows = result.get("values", [])
    if len(rows) < 2:
        return []

    # Columns: A=ICCID, B=Dirección IP, C=NUMERO, D=Plan, E=IMSI, F=APN, G=Telemedida, H=Cod. Interno BIA
    ips = []
    seen = set()
    for row in rows[1:]:
        if len(row) < 8:
            continue
        ip = (row[1] if len(row) > 1 else "").strip()
        apn = (row[5] if len(row) > 5 else "").strip().lower()
        cod_interno = (row[7] if len(row) > 7 else "").strip().lower()

        if apn == "bia.claro.com.co" and cod_interno == "disponible" and ip and ip not in seen:
            ips.append(ip)
            seen.add(ip)
            if len(ips) >= cantidad:
                break

    return ips
