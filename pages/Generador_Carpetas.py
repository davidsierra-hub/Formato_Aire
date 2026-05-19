import streamlit as st
import asyncio
import os
import nest_asyncio
from dotenv import load_dotenv

load_dotenv()
nest_asyncio.apply()

from services.metabase_service import consultar_metabase, parsear_datos
from services.excel_service import procesar_excel
from services.drive_service import descargar_template, crear_o_buscar_carpeta, subir_archivo
from services.certificados_service import subir_certificados

st.title("⚡ Generador de Carpetas AIR-E")
st.markdown("Ingresa el **Contract ID** para crear automáticamente la carpeta de cumplimiento en Drive.")

st.divider()

contract_id = st.text_input(
    "ID de contrato",
    placeholder="Ej: 44705",
    max_chars=20
)

if st.button("Generar carpeta", type="primary", disabled=not contract_id.strip()):
    contract_id = contract_id.strip()

    with st.status("Generando carpeta de cumplimiento...", expanded=True) as status:
        try:
            loop = asyncio.get_event_loop()

            st.write("📡 Consultando datos del contrato...")
            records = loop.run_until_complete(consultar_metabase(contract_id))
            datos   = parsear_datos(records)
            nic     = datos["nic"]
            st.write(f"✅ Contrato encontrado — NIC: **{nic}** | {datos['razon_social']}")

            st.write("📄 Generando solicitud Excel...")
            template_bytes = descargar_template(os.getenv("TEMPLATE_ID"))
            excel_bytes    = procesar_excel(template_bytes, datos)
            st.write("✅ Excel generado")

            st.write(f"📁 Creando carpeta NIC {nic} en Drive...")
            folder_id      = crear_o_buscar_carpeta(f"NIC {nic}", os.getenv("PARENT_FOLDER_ID"))
            nombre_archivo = f"SOLICITUD DE ACOMPAÑAMIENTO AIRE - NIC {nic}.xlsx"
            subir_archivo(nombre_archivo, excel_bytes, folder_id)
            st.write("✅ Excel subido a Drive")

            st.write("📋 Subiendo certificados (Medidor / TC / TP) y memoria de cálculo...")
            certificados = loop.run_until_complete(subir_certificados(contract_id, folder_id))
            st.write(f"✅ Medidor: {len(certificados['medidor'])} archivo(s)")
            st.write(f"✅ TC: {len(certificados['tc'])} archivo(s)")
            st.write(f"✅ TP: {len(certificados['tp'])} archivo(s)")
            if certificados.get("memoria_calculo"):
                st.write("✅ Memoria de cálculo subida")
            else:
                st.write("⚠️ Memoria de cálculo no disponible para este contrato")

            status.update(label="¡Carpeta creada exitosamente!", state="complete")

            st.divider()
            st.success(f"**Carpeta NIC {nic}** lista en Google Drive")
            st.markdown(f"""
| Campo | Valor |
|---|---|
| NIC | {nic} |
| Empresa | {datos['razon_social']} |
| Tipo de medida | {datos['tipo_medida']} |
| Ciudad | {datos['ciudad']}, {datos['departamento']} |
| Excel | {nombre_archivo} |
| Medidor | {len(certificados['medidor'])} archivo(s) |
| TC | {len(certificados['tc'])} archivo(s) |
| TP | {len(certificados['tp'])} archivo(s) |
| Memoria de cálculo | {'✅ Subida' if certificados.get('memoria_calculo') else '⚠️ No disponible'} |
""")

        except ValueError as e:
            status.update(label="Error", state="error")
            st.error(f"**Contrato no encontrado:** {e}")
        except Exception as e:
            status.update(label="Error", state="error")
            st.error(f"**Error:** {e}")
