import io
import zipfile

import openpyxl
from openpyxl.styles import Font

from services.wms_serial_service import consultar_wms_por_seriales
from services.telemedida_service import obtener_ips_disponibles
from services.wms_service import descargar_pdf


def generar_excel(seriales: list, datos_wms: dict, ips: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Medidores Directa IP"

    for col, header in enumerate(["Nombre", "Serial", "Marca", "IP"], 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for i, serial in enumerate(seriales):
        dato = datos_wms.get(serial, {})
        ws.cell(row=i + 2, column=1, value=serial)
        ws.cell(row=i + 2, column=2, value=serial)
        ws.cell(row=i + 2, column=3, value=dato.get("marca") or "")
        ws.cell(row=i + 2, column=4, value=ips[i] if i < len(ips) else "")

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


async def generar_zip_calibracion(seriales: list, datos_wms: dict) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for serial in seriales:
            url = datos_wms.get(serial, {}).get("certificado_calibracion")
            if url:
                pdf_bytes = await descargar_pdf(url)
                zf.writestr(f"{serial}.pdf", pdf_bytes)
    zip_buffer.seek(0)
    return zip_buffer.read()


async def obtener_certificado_conformidad(seriales: list, datos_wms: dict) -> bytes | None:
    for serial in seriales:
        url = datos_wms.get(serial, {}).get("certificado_conformidad")
        if url:
            return await descargar_pdf(url)
    return None


async def procesar_medidores_directa(seriales: list) -> dict:
    datos_wms = await consultar_wms_por_seriales(seriales)
    ips = obtener_ips_disponibles(len(seriales))

    excel_bytes = generar_excel(seriales, datos_wms, ips)
    zip_bytes = await generar_zip_calibracion(seriales, datos_wms)
    conformidad_bytes = await obtener_certificado_conformidad(seriales, datos_wms)

    return {
        "excel": excel_bytes,
        "zip": zip_bytes,
        "conformidad": conformidad_bytes,
        "seriales_encontrados": len(datos_wms),
        "seriales_no_encontrados": [s for s in seriales if s not in datos_wms],
        "ips_asignadas": len(ips),
    }
