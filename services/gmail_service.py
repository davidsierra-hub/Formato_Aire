"""
Servicio Gmail — dos modos:

  1. crear_borrador_gmail()  — Crea un borrador real en Gmail vía API.
                              Requiere gmail_token.json (generado con
                              authorize_gmail.py).

  2. generar_eml()           — Fallback portable. Genera archivo .eml
                              descargable que se abre con el cliente
                              de correo predeterminado.
"""

import base64
import os
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
TOKEN_FILE = "gmail_token.json"

ASUNTO_DEFAULT = "Simulación Cambio de Nivel de Tensión — {razon_social}"

CUERPO_DEFAULT = """Cordial saludo,

Adjunto encontrarás la simulación financiera del proyecto de cambio de nivel de tensión para tu cuenta. Cualquier inquietud quedamos atentos.

Equipo Bia
"""


def _build_message(
    razon_social:  str,
    pdf_bytes:     bytes,
    pdf_filename:  str,
    destinatario:  str = "",
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = ASUNTO_DEFAULT.format(razon_social=razon_social or "")
    if destinatario:
        msg["To"] = destinatario
    msg.set_content(CUERPO_DEFAULT)
    msg.add_attachment(
        pdf_bytes,
        maintype = "application",
        subtype  = "pdf",
        filename = pdf_filename,
    )
    return msg


# ---------------------------------------------------------------------------
# Modo 1: borrador real en Gmail (OAuth de usuario)
# ---------------------------------------------------------------------------
def _token_path() -> str:
    return os.getenv("GMAIL_TOKEN_PATH", TOKEN_FILE)


def gmail_autorizado() -> bool:
    """True si existe el token y se puede crear borradores sin más interacción."""
    return os.path.exists(_token_path())


def _load_creds() -> Credentials:
    path = _token_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No se encontró {path}. Corre primero `python authorize_gmail.py` "
            "para autorizar Gmail con operaciones@bia.app."
        )
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def crear_borrador_gmail(
    razon_social:  str,
    pdf_bytes:     bytes,
    pdf_filename:  str,
    destinatario:  str = "",
) -> dict:
    """
    Crea un borrador en Gmail con el PDF adjunto.

    Returns:
        {"id": draft_id, "url": link al borrador en Gmail web}
    """
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    msg = _build_message(razon_social, pdf_bytes, pdf_filename, destinatario)
    raw = base64.urlsafe_b64encode(bytes(msg)).decode("utf-8")

    draft = service.users().drafts().create(
        userId = "me",
        body   = {"message": {"raw": raw}},
    ).execute()

    return {
        "id":  draft["id"],
        "url": "https://mail.google.com/mail/u/0/#drafts",
    }


# ---------------------------------------------------------------------------
# Borrador genérico (varios destinatarios + varios adjuntos + HTML + firma)
# ---------------------------------------------------------------------------
def _obtener_firma_html(service) -> str:
    """Lee la firma del sendAs primario del usuario autorizado.
    Devuelve string HTML (puede ser '' si el usuario no tiene firma)."""
    try:
        res = service.users().settings().sendAs().list(userId="me").execute()
    except Exception:
        return ""
    for s in res.get("sendAs", []):
        if s.get("isPrimary"):
            return s.get("signature", "") or ""
    # fallback: primer sendAs disponible
    items = res.get("sendAs", [])
    return items[0].get("signature", "") if items else ""


def _cuerpo_a_html(cuerpo_plano: str) -> str:
    """Convierte un cuerpo en texto plano a HTML con fuente estándar Arial.
    Preserva saltos de línea y bullets de tipo '• …'."""
    from html import escape
    lineas_html = []
    for linea in cuerpo_plano.split("\n"):
        if not linea.strip():
            lineas_html.append("<br>")
        else:
            lineas_html.append(escape(linea) + "<br>")
    cuerpo = "\n".join(lineas_html)
    return (
        '<div style="font-family: Verdana, Geneva, sans-serif; '
        'font-size: small;">'
        f"{cuerpo}"
        "</div>"
    )


def crear_borrador_multi(
    asunto:        str,
    cuerpo:        str,
    destinatarios: list[str],
    adjuntos:      list[tuple[str, bytes]],  # [(filename, bytes), ...]
) -> dict:
    """Crea un borrador en Gmail con N destinatarios y N adjuntos PDF.
    El cuerpo se manda como HTML (fuente Arial) y se anexa la firma
    corporativa del usuario autorizado.

    Returns:
        {"id": draft_id, "url": link al borrador en Gmail web}
    """
    creds = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    cuerpo_html = _cuerpo_a_html(cuerpo)
    firma_html = _obtener_firma_html(service)
    if firma_html:
        cuerpo_html += f'<br>{firma_html}'

    msg = EmailMessage()
    msg["Subject"] = asunto
    if destinatarios:
        msg["To"] = ", ".join(destinatarios)
    msg.set_content(cuerpo)               # fallback plano para clientes sin HTML
    msg.add_alternative(cuerpo_html, subtype="html")
    for filename, contenido in adjuntos:
        msg.add_attachment(
            contenido,
            maintype="application",
            subtype="pdf",
            filename=filename,
        )

    raw = base64.urlsafe_b64encode(bytes(msg)).decode("utf-8")
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()
    return {
        "id":  draft["id"],
        "url": f"https://mail.google.com/mail/u/0/#drafts/{draft['id']}",
    }


# ---------------------------------------------------------------------------
# Modo 2: archivo .eml descargable (fallback)
# ---------------------------------------------------------------------------
def generar_eml(
    razon_social:  str,
    pdf_bytes:     bytes,
    pdf_filename:  str,
    destinatario:  str = "",
    remitente:     str = "operaciones@bia.app",
) -> bytes:
    """Construye un archivo .eml listo para abrir con el PDF adjunto."""
    msg = _build_message(razon_social, pdf_bytes, pdf_filename, destinatario)
    msg["From"] = remitente
    return bytes(msg)
