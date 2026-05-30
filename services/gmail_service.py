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
    "https://www.googleapis.com/auth/gmail.readonly",  # leer sent + threads para bot seguimiento
]
TOKEN_FILE = "gmail_token.json"

ASUNTO_DEFAULT = "Cambio de Nivel de Tensión — {razon_social}"

CUERPO_DEFAULT = """Cordial saludo, equipo {razon_social}

Por medio del presente compartimos la información relacionada con el proyecto de Cambio de Nivel de Tensión, incluyendo:

• Costo estimado del proyecto.
• Marco técnico y regulatorio que sustenta el requerimiento.
• Simulación del retorno de inversión estimado en meses.
• Ahorro mensual promedio proyectado.

Queremos resaltar que el cambio de nivel de tensión **no corresponde a una exigencia de BIA Energy,** sino a un requisito establecido por la regulación vigente para poder realizar el cambio de comercializador, dadas las condiciones actuales de la cuenta.

En este sentido, el proyecto permitirá dar cumplimiento a la normatividad aplicable y habilitar la viabilidad del proceso de migración.

Quedamos atentos a cualquier inquietud, comentario o validación requerida para continuar avanzando con el proceso.

Cordialmente,
"""


def _build_message(
    razon_social:  str,
    pdf_bytes:     bytes,
    pdf_filename:  str,
    destinatario:  str = "",
) -> EmailMessage:
    rs = razon_social or ""
    msg = EmailMessage()
    msg["Subject"] = ASUNTO_DEFAULT.format(razon_social=rs)
    if destinatario:
        msg["To"] = destinatario
    msg.set_content(CUERPO_DEFAULT.format(razon_social=rs))
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
    Crea un borrador en Gmail con el PDF adjunto. El cuerpo se renderiza
    como HTML (Verdana) y se le anexa automáticamente la firma corporativa
    del usuario autorizado (la que tenga configurada en Gmail Settings).

    Returns:
        {"id": draft_id, "url": link al borrador en Gmail web}
    """
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    rs           = razon_social or ""
    asunto       = ASUNTO_DEFAULT.format(razon_social=rs)
    cuerpo_plano = CUERPO_DEFAULT.format(razon_social=rs)

    # HTML enriquecido (bullets, negrita, fuente Verdana) + firma corporativa
    cuerpo_html = _cuerpo_a_html(cuerpo_plano)
    firma_html  = _obtener_firma_html(service)
    if firma_html:
        cuerpo_html += f"<br>{firma_html}"

    msg = EmailMessage()
    msg["Subject"] = asunto
    if destinatario:
        msg["To"] = destinatario
    msg.set_content(cuerpo_plano)                          # fallback texto plano
    msg.add_alternative(cuerpo_html, subtype="html")        # render principal
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
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


def _aplicar_negrita(texto_escapado: str) -> str:
    """Convierte **texto** en <b>texto</b>. Asume input ya html-escaped."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto_escapado)


def _cuerpo_a_html(cuerpo_plano: str) -> str:
    """Convierte texto plano a HTML con fuente Verdana. Soporta:
       - Bullets: líneas que empiezan con '• ' (se agrupan en <ul><li>)
       - Negrita: texto entre **...** se vuelve <b>...</b>
       - Saltos de línea: cada línea termina en <br>; las vacías son <br> solo.
    """
    from html import escape
    out = []
    en_lista = False

    for linea in cuerpo_plano.split("\n"):
        linea_stripped = linea.strip()
        es_bullet = linea_stripped.startswith("• ")

        if es_bullet:
            if not en_lista:
                out.append("<ul>")
                en_lista = True
            contenido = linea_stripped[2:].strip()
            out.append(f"  <li>{_aplicar_negrita(escape(contenido))}</li>")
            continue

        if en_lista:
            out.append("</ul>")
            en_lista = False

        if not linea_stripped:
            out.append("<br>")
        else:
            out.append(f"{_aplicar_negrita(escape(linea_stripped))}<br>")

    if en_lista:
        out.append("</ul>")

    cuerpo = "\n".join(out)
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
# Lectura de Gmail (sent + threads) — usado por el bot de seguimiento
# ---------------------------------------------------------------------------
def mi_email() -> str:
    """Devuelve el email de la cuenta autorizada (operaciones@bia.app)."""
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)
    return service.users().getProfile(userId="me").execute()["emailAddress"]


def listar_sent_simulaciones(query_extra: str = "") -> list[dict]:
    """
    Lista correos enviados desde Gmail que correspondan a simulaciones NT2.

    Patrón: subject empieza con "Cambio de Nivel de Tensión —".
    Devuelve un dict por thread (no por mensaje), con thread_id, to, subject,
    fecha (unix timestamp seconds), message_id del primer mensaje.
    """
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    q = 'in:sent subject:"Cambio de Nivel de Tensión"'
    if query_extra:
        q += " " + query_extra

    res = service.users().messages().list(userId="me", q=q, maxResults=200).execute()
    messages = res.get("messages", [])

    salidas      = []
    threads_seen = set()
    for m in messages:
        tid = m["threadId"]
        if tid in threads_seen:
            continue
        threads_seen.add(tid)

        msg = service.users().messages().get(
            userId           = "me",
            id               = m["id"],
            format           = "metadata",
            metadataHeaders  = ["To", "Subject", "Date", "Message-ID"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

        salidas.append({
            "thread_id":     tid,
            "message_id":    m["id"],
            "to":            headers.get("To", ""),
            "subject":       headers.get("Subject", ""),
            "rfc_message_id": headers.get("Message-ID", ""),
            "internal_date": int(msg.get("internalDate", 0)) / 1000,
        })
    return salidas


def thread_tiene_respuesta_externa(thread_id: str, mi_email_addr: str) -> tuple[bool, str | None]:
    """
    True si hay al menos un mensaje en el hilo cuyo From: NO es mi_email_addr.

    Devuelve (tiene_respuesta, internal_date_ultimo_externo).
    """
    import re
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    thread = service.users().threads().get(
        userId          = "me",
        id              = thread_id,
        format          = "metadata",
        metadataHeaders = ["From"],
    ).execute()

    mi_lower = mi_email_addr.lower()
    for msg in thread.get("messages", []):
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        frm     = headers.get("From", "")
        match   = re.search(r"<(.+?)>", frm)
        sender  = (match.group(1) if match else frm).strip().lower()
        if sender and sender != mi_lower:
            return True, msg.get("internalDate")
    return False, None


def _ultimo_message_rfc_id(thread_id: str) -> str | None:
    """Message-ID (header RFC) del último mensaje del hilo, para usar como In-Reply-To."""
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)
    thread  = service.users().threads().get(
        userId          = "me",
        id              = thread_id,
        format          = "metadata",
        metadataHeaders = ["Message-ID"],
    ).execute()
    msgs = thread.get("messages", [])
    if not msgs:
        return None
    headers = {h["name"]: h["value"] for h in msgs[-1]["payload"]["headers"]}
    return headers.get("Message-ID")


def crear_borrador_seguimiento(
    thread_id:     str,
    razon_social:  str,
    cuerpo_plano:  str,            # plantilla con {razon_social} y opcionalmente otros
    **placeholders,                # otros placeholders adicionales (ej. fecha)
) -> dict:
    """
    Crea un borrador de respuesta dentro del mismo hilo. El cuerpo se renderiza
    como HTML (Verdana, con bullets/negrita) y se le anexa la firma corporativa.
    El subject queda como "Re: Cambio de Nivel de Tensión — {razon_social}".

    Cualquier kwarg extra se pasa al .format() del cuerpo (ej. fecha="30 de mayo").

    Returns:
        {"id": draft_id, "url": link al borrador en Gmail web}
    """
    creds   = _load_creds()
    service = build("gmail", "v1", credentials=creds)

    rs           = razon_social or ""
    cuerpo_txt   = cuerpo_plano.format(razon_social=rs, **placeholders)
    cuerpo_html  = _cuerpo_a_html(cuerpo_txt)
    firma_html   = _obtener_firma_html(service)
    if firma_html:
        cuerpo_html += f"<br>{firma_html}"

    asunto = f"Re: Cambio de Nivel de Tensión — {rs}"
    in_reply_to = _ultimo_message_rfc_id(thread_id)

    msg = EmailMessage()
    msg["Subject"] = asunto
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"]  = in_reply_to
    msg.set_content(cuerpo_txt)
    msg.add_alternative(cuerpo_html, subtype="html")

    raw   = base64.urlsafe_b64encode(bytes(msg)).decode("utf-8")
    draft = service.users().drafts().create(
        userId = "me",
        body   = {"message": {"raw": raw, "threadId": thread_id}},
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
    remitente:     str = "david.sierra@bia.app",
) -> bytes:
    """Construye un archivo .eml listo para abrir con el PDF adjunto."""
    msg = _build_message(razon_social, pdf_bytes, pdf_filename, destinatario)
    msg["From"] = remitente
    return bytes(msg)
