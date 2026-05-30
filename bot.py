"""
Bot de seguimiento de correos de simulación NT2.

Conecta a Slack vía Socket Mode (no necesita endpoint HTTPS público).
Cada hora revisa Gmail buscando:
  1. Nuevos correos enviados con asunto "Cambio de Nivel de Tensión —"
     → los registra en la Sheet de seguimientos y avisa por Slack.
  2. Respuestas externas en hilos ya registrados → notifica por Slack.
  3. Casos con `proximo_recordatorio` vencido → manda Slack con botones.

Los clicks en los botones (Sí enviar / Posponer / Marcar respondido) llegan
en tiempo real vía WebSocket y se procesan acá mismo.

Uso:
    python bot.py

Para arranque automático al encender el PC, crear un acceso directo en:
    shell:startup    (Win+R)
"""

import logging
import os
import re
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from services.gmail_service import (
    crear_borrador_seguimiento,
    listar_sent_simulaciones,
    mi_email,
    thread_tiene_respuesta_externa,
)
from services.seguimiento_service import (
    actualizar_caso,
    agregar_caso,
    buscar_caso_por_thread,
    listar_casos,
)
from services.slack_service import (
    mensaje_directo,
    notificar_desistido,
    notificar_nuevo_envio,
    notificar_recordatorio_seguimiento,
    notificar_respuesta,
)


logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("nt2-bot")


# ---------------------------------------------------------------------------
# Cuerpos de los correos de seguimiento
# ---------------------------------------------------------------------------
SEGUIMIENTO_1_BODY = """Cordial saludo, equipo {razon_social}:

Esperamos que se encuentren muy bien.

Dando seguimiento a la comunicación enviada el pasado {fecha}, relacionada con el proyecto de Cambio de Nivel de Tensión, queremos consultar si tuvieron oportunidad de revisar la información compartida referente al costo estimado del proyecto, el marco regulatorio aplicable y la proyección de retorno de inversión.

Agradeceríamos nos pudieran informar sus comentarios o la decisión frente a esta iniciativa, teniendo en cuenta que el cambio de nivel de tensión constituye un requisito regulatorio para avanzar con el proceso de cambio de comercializador bajo las condiciones actuales de la cuenta.

Quedamos atentos a cualquier inquietud o información adicional que requieran para apoyar su proceso de evaluación.

Muchas gracias por su atención.

Cordialmente,
"""

SEGUIMIENTO_2_BODY = """Cordial saludo, equipo {razon_social}:

Esperamos que se encuentren muy bien.

Dando continuidad a las comunicaciones enviadas previamente respecto al proyecto de Cambio de Nivel de Tensión requerido para avanzar con el proceso de cambio de comercializador, y al no haber recibido comentarios o retroalimentación por parte de su equipo, entenderemos que no existe interés en continuar con esta gestión por el momento.

En consecuencia, daremos por desistido el proceso asociado a esta solicitud y procederemos a cerrar el seguimiento interno correspondiente.

Sin embargo, queremos reiterar que nuestro equipo permanecerá a su disposición para retomar la evaluación o brindar el acompañamiento requerido en caso de que más adelante deseen reconsiderar esta iniciativa o resolver cualquier inquietud relacionada con el proyecto.

Agradecemos el tiempo y la atención brindados durante este proceso, y quedamos atentos a poder apoyarlos en futuras oportunidades.

Cordialmente,
"""


_MESES_ES = {
    1: "enero",   2: "febrero",   3: "marzo",     4: "abril",
    5: "mayo",    6: "junio",     7: "julio",     8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _fecha_humana(fecha_iso: str) -> str:
    """De '2026-05-30' devuelve '30 de mayo de 2026'. Fallback al string raw."""
    try:
        d = datetime.strptime(fecha_iso, "%Y-%m-%d")
        return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"
    except (ValueError, KeyError):
        return fecha_iso


# ---------------------------------------------------------------------------
# Slack app (Socket Mode)
# ---------------------------------------------------------------------------
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


def _extraer_thread_id(value: str) -> str:
    """El value de los botones puede ser 'tipo|thread_id' o solo 'thread_id'."""
    return value.split("|", 1)[1] if "|" in value else value


@app.action("aprobar_seguimiento_1")
def aprobar_seguimiento_1(ack, body, client):
    ack()
    thread_id = _extraer_thread_id(body["actions"][0]["value"])
    caso = buscar_caso_por_thread(thread_id)
    if not caso:
        client.chat_postMessage(channel=body["user"]["id"], text="❌ Caso no encontrado en la Sheet.")
        return
    try:
        draft = crear_borrador_seguimiento(
            thread_id,
            caso["razon_social"],
            SEGUIMIENTO_1_BODY,
            fecha=_fecha_humana(caso.get("fecha_envio", "")),
        )
        actualizar_caso(thread_id, {
            "estado":               "seguimiento1_enviado",
            "proximo_recordatorio": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
            "notas":                f"Seguimiento 1 creado el {datetime.now():%Y-%m-%d %H:%M}",
        })
        client.chat_postMessage(
            channel = body["user"]["id"],
            text    = f"✅ Borrador de seguimiento creado para *{caso['razon_social']}*.\n<{draft['url']}|Abrir en Gmail>",
            unfurl_links = False,
        )
    except Exception as e:
        log.exception("Error creando seguimiento 1")
        client.chat_postMessage(channel=body["user"]["id"], text=f"❌ Error: {e}")


@app.action("aprobar_seguimiento_2")
def aprobar_seguimiento_2(ack, body, client):
    ack()
    thread_id = _extraer_thread_id(body["actions"][0]["value"])
    caso = buscar_caso_por_thread(thread_id)
    if not caso:
        client.chat_postMessage(channel=body["user"]["id"], text="❌ Caso no encontrado en la Sheet.")
        return
    try:
        draft = crear_borrador_seguimiento(thread_id, caso["razon_social"], SEGUIMIENTO_2_BODY)
        actualizar_caso(thread_id, {
            "estado":               "seguimiento2_enviado",
            "proximo_recordatorio": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
            "notas":                f"Seguimiento FINAL creado el {datetime.now():%Y-%m-%d %H:%M}",
        })
        client.chat_postMessage(
            channel = body["user"]["id"],
            text    = f"✅ Borrador FINAL creado para *{caso['razon_social']}*.\n<{draft['url']}|Abrir en Gmail>",
            unfurl_links = False,
        )
    except Exception as e:
        log.exception("Error creando seguimiento 2")
        client.chat_postMessage(channel=body["user"]["id"], text=f"❌ Error: {e}")


@app.action("posponer_seguimiento")
def posponer_seguimiento(ack, body, client):
    ack()
    thread_id = _extraer_thread_id(body["actions"][0]["value"])
    actualizar_caso(thread_id, {
        "proximo_recordatorio": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "notas":                "Recordatorio pospuesto +7 días por el usuario",
    })
    client.chat_postMessage(channel=body["user"]["id"], text="⏭ Recordatorio reagendado para dentro de 7 días.")


@app.action("marcar_respondido")
def marcar_respondido(ack, body, client):
    ack()
    thread_id = _extraer_thread_id(body["actions"][0]["value"])
    actualizar_caso(thread_id, {
        "estado": "respondido",
        "notas":  "Marcado como respondido manualmente desde Slack",
    })
    client.chat_postMessage(channel=body["user"]["id"], text="✓ Caso marcado como respondido.")


# ---------------------------------------------------------------------------
# Chequeo periódico (corre cada hora)
# ---------------------------------------------------------------------------
def _extraer_email_destinatario(to_header: str) -> str:
    """De 'Nombre <email@dom>' o 'email@dom' devuelve 'email@dom' en minúsculas."""
    m = re.search(r"<(.+?)>", to_header)
    return (m.group(1) if m else to_header).strip().lower()


def _extraer_razon_social(subject: str) -> str:
    """De 'Cambio de Nivel de Tensión — XYZ' devuelve 'XYZ'."""
    if " — " in subject:
        return subject.split(" — ", 1)[1].strip()
    return subject.strip()


def _es_subject_de_automatizacion(subject: str) -> bool:
    """
    True solo si el subject empieza exactamente con el patrón que genera
    nuestra automatización: 'Cambio de Nivel de Tensión — <RAZON>'.

    Esto excluye correos manuales antiguos con asuntos como:
      - 'Envío de información - Cambio de Nivel de Tensión - Bia Energy'
      - 'Re: Oferta Comercial Cambio De Nivel De Tensión 2.'

    Tolera prefijo 'Re:' o 'Fwd:' en caso de respuestas dentro del hilo.
    """
    import re
    s = re.sub(r"^(re|fwd|fw)\s*:\s*", "", subject.lstrip(), flags=re.IGNORECASE).strip()
    return s.startswith("Cambio de Nivel de Tensión —")


ESTADOS_CERRADOS = {"respondido", "desistido"}


def chequeo_periodico() -> None:
    log.info("⏱ Iniciando chequeo periódico…")
    try:
        yo = mi_email()
    except Exception as e:
        log.exception(f"No se pudo leer Gmail (¿autorizado?): {e}")
        return

    casos_existentes = {c["thread_id"]: c for c in listar_casos()}

    # 1. Detectar nuevos enviados
    try:
        sent = listar_sent_simulaciones()
    except Exception as e:
        log.exception(f"Error leyendo sent folder: {e}")
        sent = []

    for envio in sent:
        if envio["thread_id"] in casos_existentes:
            continue
        if not _es_subject_de_automatizacion(envio["subject"]):
            log.debug(f"Skip (no match patrón): {envio['subject']!r}")
            continue
        razon = _extraer_razon_social(envio["subject"])
        email = _extraer_email_destinatario(envio["to"])
        if not email or "@" not in email:
            log.warning(f"To: vacío o inválido en thread {envio['thread_id']}: '{envio['to']}'")
            continue
        fecha = datetime.fromtimestamp(envio["internal_date"]).strftime("%Y-%m-%d")
        try:
            agregar_caso(envio["thread_id"], razon, email, fecha)
            notificar_nuevo_envio(razon, email)
            log.info(f"✓ Registrado nuevo envío: {razon} → {email}")
        except Exception as e:
            log.exception(f"Error registrando {razon}: {e}")

    # 2 + 3. Recargar tras altas, luego buscar respuestas y recordatorios
    casos = listar_casos()
    hoy   = date.today()

    for caso in casos:
        if caso["estado"] in ESTADOS_CERRADOS:
            continue

        # 2. Respuestas
        try:
            tiene_resp, _ = thread_tiene_respuesta_externa(caso["thread_id"], yo)
        except Exception as e:
            log.exception(f"Error revisando thread {caso['thread_id']}: {e}")
            continue

        if tiene_resp:
            actualizar_caso(caso["thread_id"], {
                "estado": "respondido",
                "notas":  "Respuesta detectada automáticamente en el hilo",
            })
            url = f"https://mail.google.com/mail/u/0/#all/{caso['thread_id']}"
            notificar_respuesta(caso["razon_social"], url)
            log.info(f"✓ Respuesta detectada: {caso['razon_social']}")
            continue

        # 3. Recordatorios
        rec_str = caso.get("proximo_recordatorio", "")
        if not rec_str:
            continue
        try:
            fecha_rec = datetime.strptime(rec_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if fecha_rec > hoy:
            continue

        estado = caso["estado"]
        if estado in ("enviado", "seguimiento1_pendiente"):
            notificar_recordatorio_seguimiento(
                caso["razon_social"], caso["email_cliente"], caso["thread_id"],
                tipo="seguimiento_1",
            )
            if estado == "enviado":
                actualizar_caso(caso["thread_id"], {"estado": "seguimiento1_pendiente"})
            log.info(f"→ Recordatorio seguimiento 1: {caso['razon_social']}")

        elif estado in ("seguimiento1_enviado", "seguimiento2_pendiente"):
            notificar_recordatorio_seguimiento(
                caso["razon_social"], caso["email_cliente"], caso["thread_id"],
                tipo="seguimiento_2",
            )
            if estado == "seguimiento1_enviado":
                actualizar_caso(caso["thread_id"], {"estado": "seguimiento2_pendiente"})
            log.info(f"→ Recordatorio seguimiento 2: {caso['razon_social']}")

        elif estado == "seguimiento2_enviado":
            actualizar_caso(caso["thread_id"], {
                "estado": "desistido",
                "notas":  f"Marcado desistido automáticamente el {datetime.now():%Y-%m-%d}",
            })
            notificar_desistido(caso["razon_social"])
            log.info(f"❌ Desistido: {caso['razon_social']}")

    log.info("✅ Chequeo periódico terminado.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    required = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_NOTIFY_USER_ID"]
    faltantes = [v for v in required if not os.getenv(v)]
    if faltantes:
        log.error(f"Variables faltantes en .env: {faltantes}")
        raise SystemExit(1)

    sched = BackgroundScheduler(timezone="America/Bogota")
    sched.add_job(
        chequeo_periodico,
        "interval",
        hours          = 1,
        next_run_time  = datetime.now() + timedelta(seconds=15),
    )
    sched.start()

    try:
        mensaje_directo("🤖 Bot NT2 *iniciado*. Próximo chequeo en 15s y luego cada hora.")
    except Exception as e:
        log.warning(f"No se pudo enviar mensaje de inicio a Slack: {e}")

    log.info("🤖 Bot NT2 escuchando eventos Slack (Socket Mode)…")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
