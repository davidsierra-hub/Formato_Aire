import streamlit as st
import asyncio
import nest_asyncio
from dotenv import load_dotenv

load_dotenv()
nest_asyncio.apply()

from services.medidores_directa_service import procesar_medidores_directa

st.title("📡 Cumplimiento Regulatorio — Medidores Directa")
st.markdown(
    "Ingresa los seriales de medidores de **medida directa** para generar "
    "los 3 archivos del correo a Air-e."
)

st.divider()

seriales_input = st.text_area(
    "Seriales (uno por línea)",
    height=200,
    placeholder="Ej:\n12345678\n87654321\n11223344",
)


def parse_seriales(text: str) -> list:
    return [s.strip() for s in text.strip().splitlines() if s.strip()]


seriales = parse_seriales(seriales_input)

if seriales:
    st.caption(f"{len(seriales)} serial(es) detectado(s)")

if st.button("Generar archivos", type="primary", disabled=not seriales):
    with st.status("Procesando medidores directa...", expanded=True) as status:
        try:
            loop = asyncio.get_event_loop()

            st.write("🔍 Consultando WMS General por seriales...")
            st.write("📡 Obteniendo IPs disponibles de BD_Telemedida...")

            resultado = loop.run_until_complete(procesar_medidores_directa(seriales))

            st.write(f"✅ {resultado['seriales_encontrados']} serial(es) encontrado(s) en WMS")

            if resultado["seriales_no_encontrados"]:
                st.warning(
                    f"⚠️ Seriales no encontrados en WMS: "
                    f"{', '.join(resultado['seriales_no_encontrados'])}"
                )

            if resultado["ips_asignadas"] < len(seriales):
                st.warning(
                    f"⚠️ Solo se encontraron {resultado['ips_asignadas']} IP(s) disponibles "
                    f"para {len(seriales)} serial(es)"
                )
            else:
                st.write(f"✅ {resultado['ips_asignadas']} IP(s) asignada(s) desde BD_Telemedida")

            if resultado["conformidad"]:
                st.write("✅ Certificado de Conformidad descargado")
            else:
                st.write("⚠️ Certificado de Conformidad no disponible en WMS")

            status.update(label="¡Archivos listos para descargar!", state="complete")

            st.divider()
            st.subheader("📥 Descarga los 3 archivos del correo")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.download_button(
                    label="📊 Excel",
                    data=resultado["excel"],
                    file_name="Medidores Directa IP.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.caption("Medidores Directa IP.xlsx")

            with col2:
                st.download_button(
                    label="🗜️ ZIP Calibración",
                    data=resultado["zip"],
                    file_name="medidores directa.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
                st.caption("medidores directa.zip")

            with col3:
                if resultado["conformidad"]:
                    st.download_button(
                        label="📄 Conformidad",
                        data=resultado["conformidad"],
                        file_name="Certificado Conformidad.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                    st.caption("Certificado Conformidad.pdf")
                else:
                    st.button("📄 Sin conformidad", disabled=True, use_container_width=True)
                    st.caption("No disponible en WMS")

        except Exception as e:
            status.update(label="Error al procesar", state="error")
            st.error(f"**Error:** {e}")
