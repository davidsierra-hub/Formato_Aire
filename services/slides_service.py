"""
Servicio para manipular la plantilla de Google Slides "Cambio de Nivel de Tensión":
  1. Copia la plantilla a la carpeta destino (Shared Drive Nivel de Tensión).
  2. Hace replaceAllText con los placeholders {{...}}.
  3. Exporta como PDF.

Usa una service account distinta (NT2_CREDENTIALS_PATH) porque la SA del flujo
principal vive en otro proyecto GCP donde no se pudo habilitar la Slides API.

La copia queda en Drive (no se borra) para que el equipo pueda revisarla/editarla
luego con el nombre del cliente.
"""

import os

from services.drive_service import (
    get_slides_service,
    get_drive_service,
    copiar_archivo,
    exportar_como_pdf,
)


def _nt2_creds() -> str | None:
    """Ruta a las credenciales del proyecto NT2SLIDES (proyecto con Slides API)."""
    return os.getenv("NT2_CREDENTIALS_PATH")


def _construir_requests(placeholders: dict) -> list:
    """replaceAllText requests para batchUpdate de Slides API."""
    return [
        {
            "replaceAllText": {
                "containsText": {"text": placeholder, "matchCase": True},
                "replaceText":  str(valor),
            }
        }
        for placeholder, valor in placeholders.items()
    ]


def _borrar_archivo(file_id: str) -> None:
    """Best-effort: borra un archivo de Drive (usado para limpiar copias fallidas)."""
    try:
        get_drive_service(_nt2_creds()).files().delete(
            fileId=file_id, supportsAllDrives=True
        ).execute()
    except Exception:
        pass  # Si la limpieza falla, no enmascaramos el error original


def generar_simulacion_desde_template(
    template_id: str,
    parent_id: str,
    nombre_copia: str,
    placeholders: dict,
) -> tuple[bytes, str]:
    """
    Copia la plantilla, reemplaza placeholders y exporta a PDF.

    Si algún paso después de la copia falla, borra la copia para no dejar
    archivos huérfanos en el Shared Drive.

    Returns:
        (pdf_bytes, slides_url) — bytes del PDF y URL del archivo Slides en Drive
        (para que el equipo lo pueda abrir y editar manualmente si lo necesita).
    """
    creds_nt2 = _nt2_creds()

    # 1. Copiar la plantilla en la carpeta destino
    copia_id = copiar_archivo(template_id, nombre_copia, parent_id, creds_path=creds_nt2)

    try:
        # 2. Reemplazar placeholders vía Slides API
        slides = get_slides_service(creds_nt2)
        slides.presentations().batchUpdate(
            presentationId = copia_id,
            body           = {"requests": _construir_requests(placeholders)},
        ).execute()

        # 3. Exportar como PDF
        pdf_bytes = exportar_como_pdf(copia_id, creds_path=creds_nt2)
    except Exception:
        _borrar_archivo(copia_id)
        raise

    slides_url = f"https://docs.google.com/presentation/d/{copia_id}/edit"
    return pdf_bytes, slides_url
