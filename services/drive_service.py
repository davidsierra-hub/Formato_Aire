from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import os

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
]


def _resolve_creds_path(creds_path: str | None) -> str:
    """Si no se pasa creds_path, usa GOOGLE_CREDENTIALS_PATH (default)."""
    return creds_path or os.getenv("GOOGLE_CREDENTIALS_PATH")


def get_drive_service(creds_path: str | None = None):
    creds = service_account.Credentials.from_service_account_file(
        _resolve_creds_path(creds_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def get_sheets_service(creds_path: str | None = None):
    creds = service_account.Credentials.from_service_account_file(
        _resolve_creds_path(creds_path), scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def get_slides_service(creds_path: str | None = None):
    creds = service_account.Credentials.from_service_account_file(
        _resolve_creds_path(creds_path), scopes=SCOPES
    )
    return build("slides", "v1", credentials=creds)


def descargar_template(template_id: str, creds_path: str | None = None) -> bytes:
    service = get_drive_service(creds_path)
    request = service.files().get_media(fileId=template_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def crear_o_buscar_carpeta(nombre: str, parent_id: str, creds_path: str | None = None) -> str:
    service = get_drive_service(creds_path)
    query = (
        f"name = '{nombre}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return folder["id"]


def subir_archivo(nombre: str, contenido: bytes, folder_id: str, creds_path: str | None = None) -> str:
    service = get_drive_service(creds_path)
    metadata = {"name": nombre, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file["id"]


def obtener_pdf_de_carpeta(folder_id: str, creds_path: str | None = None) -> bytes | None:
    """Lista los archivos de una carpeta Drive y descarga el primer PDF encontrado."""
    service = get_drive_service(creds_path)
    query = (
        f"'{folder_id}' in parents and "
        f"mimeType = 'application/pdf' and "
        f"trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    if not files:
        return None
    file_id = files[0]["id"]
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def subir_bytes(nombre: str, contenido: bytes, folder_id: str, mimetype: str, creds_path: str | None = None) -> str:
    service = get_drive_service(creds_path)
    metadata = {"name": nombre, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mimetype)
    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file["id"]


def subir_pdf(nombre: str, contenido: bytes, folder_id: str, creds_path: str | None = None) -> str:
    service = get_drive_service(creds_path)
    metadata = {"name": nombre, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype="application/pdf",
    )
    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file["id"]


# ---------------------------------------------------------------------------
# Helpers usados por la página Cambio Nivel de Tensión
# ---------------------------------------------------------------------------
def listar_archivos_por_nombre(nombre: str, parent_id: str, mimetype: str | None = None, creds_path: str | None = None) -> list:
    """Lista archivos con un nombre exacto dentro de una carpeta/Shared Drive."""
    service = get_drive_service(creds_path)
    nombre_safe = nombre.replace("'", "\\'")
    q = f"name = '{nombre_safe}' and '{parent_id}' in parents and trashed = false"
    if mimetype:
        q += f" and mimeType = '{mimetype}'"
    results = service.files().list(
        q=q,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return results.get("files", [])


def descargar_archivo(file_id: str, creds_path: str | None = None) -> bytes:
    """Descarga el contenido binario de un archivo de Drive por ID."""
    service = get_drive_service(creds_path)
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def actualizar_archivo(file_id: str, contenido: bytes, mimetype: str, creds_path: str | None = None) -> str:
    """Reemplaza el contenido de un archivo existente en Drive."""
    service = get_drive_service(creds_path)
    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mimetype)
    service.files().update(
        fileId=file_id,
        media_body=media,
        supportsAllDrives=True,
    ).execute()
    return file_id


def copiar_archivo(source_id: str, nuevo_nombre: str, parent_id: str, creds_path: str | None = None) -> str:
    """Copia un archivo (típicamente una plantilla Slides) a una carpeta."""
    service = get_drive_service(creds_path)
    metadata = {"name": nuevo_nombre, "parents": [parent_id]}
    copia = service.files().copy(
        fileId=source_id,
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return copia["id"]


def exportar_como_pdf(file_id: str, creds_path: str | None = None) -> bytes:
    """Exporta un Google Slides/Docs como PDF."""
    service = get_drive_service(creds_path)
    request = service.files().export_media(fileId=file_id, mimeType="application/pdf")
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def eliminar_archivo(file_id: str, creds_path: str | None = None) -> None:
    """Mueve un archivo a la Papelera del Shared Drive.

    Nota: usamos `trashed=True` (update) en vez de `delete()` permanente porque
    el rol Content Manager NO permite borrado definitivo en Shared Drives —
    solo el rol Manager puede. canTrash sí está disponible. La papelera de
    Shared Drives se vacía automáticamente a los 30 días.
    """
    service = get_drive_service(creds_path)
    service.files().update(
        fileId=file_id,
        body={"trashed": True},
        supportsAllDrives=True,
    ).execute()
