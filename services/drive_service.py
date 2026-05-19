from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io
import os

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_CREDENTIALS_PATH"), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def descargar_template(template_id: str) -> bytes:
    service = get_drive_service()
    request = service.files().get_media(fileId=template_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()


def crear_o_buscar_carpeta(nombre: str, parent_id: str) -> str:
    service = get_drive_service()
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


def subir_archivo(nombre: str, contenido: bytes, folder_id: str) -> str:
    service = get_drive_service()
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


def obtener_pdf_de_carpeta(folder_id: str) -> bytes | None:
    """Lista los archivos de una carpeta Drive y descarga el primer PDF encontrado."""
    service = get_drive_service()
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


def subir_pdf(nombre: str, contenido: bytes, folder_id: str) -> str:
    service = get_drive_service()
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
