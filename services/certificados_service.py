from services.wms_service import consultar_wms, descargar_pdf
from services.drive_service import crear_o_buscar_carpeta, subir_pdf, obtener_pdf_de_carpeta
from services.alcances_service import consultar_alcances, extraer_folder_id


async def subir_memoria_calculo(contract_id: str, nic_folder_id: str) -> str | None:
    """
    Consulta Alcances General, obtiene el link de la carpeta con la memoria de cálculo,
    descarga el PDF y lo sube a la carpeta NIC.
    """
    alcance = await consultar_alcances(contract_id)
    if not alcance:
        return None

    enlace = alcance.get("enlace_memoria_de_calculo")
    if not enlace:
        return None

    folder_id = extraer_folder_id(enlace)
    if not folder_id:
        return None

    pdf_bytes = obtener_pdf_de_carpeta(folder_id)
    if not pdf_bytes:
        return None

    subir_pdf("Memoria de Calculo.pdf", pdf_bytes, nic_folder_id)
    return "Memoria de Calculo.pdf"


async def subir_certificados(contract_id: str, nic_folder_id: str) -> dict:
    """
    Consulta Wms General, crea subcarpetas Medidor/TC/TP dentro de la carpeta NIC
    y sube los PDFs de conformidad y calibración correspondientes.
    """
    wms = await consultar_wms(contract_id)
    resultado = {"medidor": [], "tc": [], "tp": []}

    # ── Medidor ───────────────────────────────────────────────────────────────
    if wms["medidores"]:
        folder_med = crear_o_buscar_carpeta("Medidor", nic_folder_id)
        equipo = wms["medidores"][0]

        if equipo.get("certificado_conformidad"):
            pdf = await descargar_pdf(equipo["certificado_conformidad"])
            subir_pdf("Conformidad.pdf", pdf, folder_med)
            resultado["medidor"].append("Conformidad.pdf")

        if equipo.get("certificado_calibracion"):
            serial = equipo.get("serial") or "SIN_SERIAL"
            nombre = f"Calibracion_{serial}.pdf"
            pdf = await descargar_pdf(equipo["certificado_calibracion"])
            subir_pdf(nombre, pdf, folder_med)
            resultado["medidor"].append(nombre)

    # ── TCs ───────────────────────────────────────────────────────────────────
    if wms["tcs"]:
        folder_tc = crear_o_buscar_carpeta("TC", nic_folder_id)

        # Un solo PDF de conformidad (del primer TC, todos comparten el mismo SKU)
        primero = wms["tcs"][0]
        if primero.get("certificado_conformidad"):
            pdf = await descargar_pdf(primero["certificado_conformidad"])
            subir_pdf("Conformidad.pdf", pdf, folder_tc)
            resultado["tc"].append("Conformidad.pdf")

        # Un PDF de calibración por cada TC
        for tc in wms["tcs"]:
            if tc.get("certificado_calibracion"):
                serial = tc.get("serial") or "SIN_SERIAL"
                nombre = f"Calibracion_{serial}.pdf"
                pdf = await descargar_pdf(tc["certificado_calibracion"])
                subir_pdf(nombre, pdf, folder_tc)
                resultado["tc"].append(nombre)

    # ── TPs ───────────────────────────────────────────────────────────────────
    if wms["tps"]:
        folder_tp = crear_o_buscar_carpeta("TP", nic_folder_id)

        # Un solo PDF de conformidad
        primero = wms["tps"][0]
        if primero.get("certificado_conformidad"):
            pdf = await descargar_pdf(primero["certificado_conformidad"])
            subir_pdf("Conformidad.pdf", pdf, folder_tp)
            resultado["tp"].append("Conformidad.pdf")

        # Un PDF de calibración por cada TP
        for tp in wms["tps"]:
            if tp.get("certificado_calibracion"):
                serial = tp.get("serial") or "SIN_SERIAL"
                nombre = f"Calibracion_{serial}.pdf"
                pdf = await descargar_pdf(tp["certificado_calibracion"])
                subir_pdf(nombre, pdf, folder_tp)
                resultado["tp"].append(nombre)

    # ── Memoria de cálculo ────────────────────────────────────────────────────
    memoria = await subir_memoria_calculo(contract_id, nic_folder_id)
    resultado["memoria_calculo"] = memoria

    return resultado
