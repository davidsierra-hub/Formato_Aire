"""
State storage para el bot de seguimiento NT2.

Almacena cada caso en un Google Sheet nativo llamado "Seguimientos NT2"
dentro del Shared Drive Nivel de Tensión. Usa Sheets API (no XLSX) para
poder hacer append/update por celda sin descargar/subir todo el archivo
cada vez.

Estados del caso (columna `estado`):
  enviado                → primer correo enviado, esperando respuesta o 14 días
  respondido             → cliente respondió en el hilo
  seguimiento1_pendiente → recordatorio mostrado, esperando decisión en Slack
  seguimiento1_enviado   → borrador de primer seguimiento creado
  seguimiento2_pendiente → recordatorio mostrado para el final
  seguimiento2_enviado   → borrador final creado
  desistido              → 3 correos sin respuesta, caso cerrado
"""

import os
from datetime import datetime, timedelta

from services.drive_service import get_drive_service, get_sheets_service


SHEET_NAME = "Seguimientos NT2"
TAB_NAME   = "Casos"

HEADERS = [
    "thread_id",
    "razon_social",
    "email_cliente",
    "fecha_envio",
    "estado",
    "proximo_recordatorio",
    "ultima_actualizacion",
    "notas",
]


def _nt2_creds() -> str | None:
    return os.getenv("NT2_CREDENTIALS_PATH")


def _parent_drive_id() -> str:
    pid = os.getenv("NIVEL_TENSION_PARENT_ID")
    if not pid:
        raise ValueError("NIVEL_TENSION_PARENT_ID no configurado en .env")
    return pid


# ---------------------------------------------------------------------------
# Spreadsheet bootstrap
# ---------------------------------------------------------------------------
def obtener_o_crear_sheet() -> str:
    """Devuelve el sheet_id del Google Sheet de seguimientos. Lo crea si no existe."""
    drive     = get_drive_service(_nt2_creds())
    parent_id = _parent_drive_id()

    q = (
        f"name = '{SHEET_NAME}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.spreadsheet' and "
        f"trashed = false"
    )
    res = drive.files().list(
        q                       = q,
        fields                  = "files(id)",
        supportsAllDrives       = True,
        includeItemsFromAllDrives = True,
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    # Crear nuevo Google Sheet
    metadata = {
        "name":     SHEET_NAME,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents":  [parent_id],
    }
    nuevo     = drive.files().create(
        body              = metadata,
        fields            = "id",
        supportsAllDrives = True,
    ).execute()
    sheet_id = nuevo["id"]

    # Renombrar la pestaña por defecto y agregar headers
    sheets = get_sheets_service(_nt2_creds())
    sheets.spreadsheets().batchUpdate(
        spreadsheetId = sheet_id,
        body          = {"requests": [{
            "updateSheetProperties": {
                "properties": {"sheetId": 0, "title": TAB_NAME},
                "fields":     "title",
            }
        }]},
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId    = sheet_id,
        range            = f"{TAB_NAME}!A1",
        valueInputOption = "RAW",
        body             = {"values": [HEADERS]},
    ).execute()
    return sheet_id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def listar_casos() -> list[dict]:
    """Devuelve todos los casos como lista de dicts."""
    sheet_id = obtener_o_crear_sheet()
    sheets   = get_sheets_service(_nt2_creds())
    res      = sheets.spreadsheets().values().get(
        spreadsheetId = sheet_id,
        range         = f"{TAB_NAME}!A2:H",
    ).execute()
    rows = res.get("values", [])

    casos = []
    for r in rows:
        r = r + [""] * (len(HEADERS) - len(r))
        casos.append(dict(zip(HEADERS, r)))
    return casos


def buscar_caso_por_thread(thread_id: str) -> dict | None:
    for c in listar_casos():
        if c["thread_id"] == thread_id:
            return c
    return None


def agregar_caso(
    thread_id:     str,
    razon_social:  str,
    email_cliente: str,
    fecha_envio:   str,  # YYYY-MM-DD
    dias_hasta_seguimiento: int = 14,
) -> None:
    """Inserta una fila nueva con estado='enviado' y recordatorio a +14 días."""
    sheet_id   = obtener_o_crear_sheet()
    sheets     = get_sheets_service(_nt2_creds())
    proximo    = (
        datetime.strptime(fecha_envio, "%Y-%m-%d") + timedelta(days=dias_hasta_seguimiento)
    ).strftime("%Y-%m-%d")
    fila = [
        thread_id,
        razon_social,
        email_cliente,
        fecha_envio,
        "enviado",
        proximo,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]
    sheets.spreadsheets().values().append(
        spreadsheetId    = sheet_id,
        range            = f"{TAB_NAME}!A:H",
        valueInputOption = "RAW",
        body             = {"values": [fila]},
    ).execute()


def actualizar_caso(thread_id: str, updates: dict) -> bool:
    """
    Aplica updates (dict columna→valor) sobre la fila del thread.
    Devuelve True si se actualizó, False si no se encontró el caso.
    """
    sheet_id = obtener_o_crear_sheet()
    sheets   = get_sheets_service(_nt2_creds())

    res  = sheets.spreadsheets().values().get(
        spreadsheetId = sheet_id,
        range         = f"{TAB_NAME}!A:H",
    ).execute()
    rows = res.get("values", [])

    row_idx = None
    for i, r in enumerate(rows[1:], start=2):  # 1-indexed; skip header
        if r and r[0] == thread_id:
            row_idx = i
            break
    if not row_idx:
        return False

    actual = rows[row_idx - 1] + [""] * (len(HEADERS) - len(rows[row_idx - 1]))
    caso   = dict(zip(HEADERS, actual))
    caso.update(updates)
    caso["ultima_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nueva = [caso[k] for k in HEADERS]

    sheets.spreadsheets().values().update(
        spreadsheetId    = sheet_id,
        range            = f"{TAB_NAME}!A{row_idx}:H{row_idx}",
        valueInputOption = "RAW",
        body             = {"values": [nueva]},
    ).execute()
    return True
