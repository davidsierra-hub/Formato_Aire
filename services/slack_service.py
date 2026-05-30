"""
Wrappers Slack para el bot de seguimiento NT2.

Las notificaciones van por DM al usuario configurado en SLACK_NOTIFY_USER_ID
(formato 'U0...' — se obtiene desde Slack profile → 'More' → 'Copy member ID').
"""

import os
from slack_sdk import WebClient


def _client() -> WebClient:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN no configurado en .env")
    return WebClient(token=token)


def _channel() -> str:
    ch = os.getenv("SLACK_NOTIFY_USER_ID")
    if not ch:
        raise ValueError("SLACK_NOTIFY_USER_ID no configurado en .env")
    return ch


# ---------------------------------------------------------------------------
# Notificaciones simples (sin botones)
# ---------------------------------------------------------------------------
def notificar_nuevo_envio(razon_social: str, email_cliente: str) -> None:
    _client().chat_postMessage(
        channel = _channel(),
        text    = f"📧 Hoy enviaste simulación NT2 a *{razon_social}* (`{email_cliente}`)",
        unfurl_links=False,
        unfurl_media=False,
    )


def notificar_respuesta(razon_social: str, thread_url: str) -> None:
    _client().chat_postMessage(
        channel = _channel(),
        text    = f"✅ {razon_social} respondió!",
        blocks  = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *{razon_social}* respondió!"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Abrir hilo"},
                    "url":  thread_url,
                },
            }
        ],
        unfurl_links=False,
        unfurl_media=False,
    )


def notificar_desistido(razon_social: str) -> None:
    _client().chat_postMessage(
        channel = _channel(),
        text    = f"❌ *{razon_social}* marcado como DESISTIDO por falta de respuesta tras 3 correos.",
    )


# ---------------------------------------------------------------------------
# Recordatorio con botones interactivos
# ---------------------------------------------------------------------------
def notificar_recordatorio_seguimiento(
    razon_social:  str,
    email_cliente: str,
    thread_id:     str,
    tipo:          str,  # 'seguimiento_1' | 'seguimiento_2'
) -> None:
    if tipo == "seguimiento_1":
        titulo    = f"⏰ *{razon_social}* lleva 14 días sin respuesta"
        subtitulo = "¿Crear borrador de seguimiento?"
    else:
        titulo    = f"⚠️ *{razon_social}* lleva 28 días sin respuesta"
        subtitulo = "¿Crear borrador FINAL avisando desistimiento si no responde en 14 días?"

    _client().chat_postMessage(
        channel = _channel(),
        text    = f"{titulo} — acciones en Slack",
        blocks  = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{titulo}\n{subtitulo}\nEmail: `{email_cliente}`",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type":      "button",
                        "style":     "primary",
                        "text":      {"type": "plain_text", "text": "✅ Sí, crear borrador"},
                        "value":     f"{tipo}|{thread_id}",
                        "action_id": f"aprobar_{tipo}",
                    },
                    {
                        "type":      "button",
                        "text":      {"type": "plain_text", "text": "⏭ Posponer 7 días"},
                        "value":     thread_id,
                        "action_id": "posponer_seguimiento",
                    },
                    {
                        "type":      "button",
                        "text":      {"type": "plain_text", "text": "✓ Marcar respondido"},
                        "value":     thread_id,
                        "action_id": "marcar_respondido",
                    },
                ],
            },
        ],
        unfurl_links=False,
        unfurl_media=False,
    )


def mensaje_directo(texto: str) -> None:
    """Helper genérico para mandar un DM al usuario configurado."""
    _client().chat_postMessage(channel=_channel(), text=texto, unfurl_links=False)
