from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()

from models import SolicitudRequest
from services.metabase_service import consultar_metabase, parsear_datos
from services.excel_service import procesar_excel
from services.drive_service import descargar_template, crear_o_buscar_carpeta, subir_archivo
from services.certificados_service import subir_certificados

app = FastAPI(title="Servicio Solicitudes AIR-E")


@app.post("/generar-solicitud")
async def generar_solicitud(req: SolicitudRequest):
    try:
        # 1. Datos del contrato y Excel
        records        = await consultar_metabase(req.contract_id)
        datos          = parsear_datos(records)
        template_bytes = descargar_template(os.getenv("TEMPLATE_ID"))
        excel_bytes    = procesar_excel(template_bytes, datos)

        # 2. Carpeta NIC y subida del Excel
        nic            = datos["nic"]
        nombre_archivo = f"SOLICITUD DE ACOMPAÑAMIENTO AIRE - NIC {nic}.xlsx"
        folder_id      = crear_o_buscar_carpeta(f"NIC {nic}", os.getenv("PARENT_FOLDER_ID"))
        file_id        = subir_archivo(nombre_archivo, excel_bytes, folder_id)

        # 3. Subcarpetas y certificados
        certificados = await subir_certificados(req.contract_id, folder_id)

        return {
            "status":        "ok",
            "archivo":       nombre_archivo,
            "folder_id":     folder_id,
            "file_id":       file_id,
            "certificados":  certificados,
        }
    except Exception as e:
        return {"status": "error", "mensaje": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}
