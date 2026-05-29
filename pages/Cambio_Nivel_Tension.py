import streamlit as st
import asyncio
import nest_asyncio
from dotenv import load_dotenv

load_dotenv()
nest_asyncio.apply()

from services.nivel_tension_service import (
    procesar_simulacion,
    operadores_red,
    formato_cop,
    formato_meses,
)
from services.gmail_service import (
    generar_eml,
    crear_borrador_gmail,
    gmail_autorizado,
)


st.title("⚡ Simulación Cambio de Nivel de Tensión")
st.markdown(
    "Genera el PDF de simulación financiera (NT1 → NT2) para una cuenta. "
    "El PPTX editable queda guardado en el Shared Drive **Nivel de Tensión** "
    "y la corrida se registra en el Excel acumulado."
)

st.divider()

col_a, col_b = st.columns(2)
with col_a:
    codigo_bia = st.text_input(
        "Código Bia de la cuenta",
        placeholder="Ej: CO0200005715",
        max_chars=30,
    )
    inversion = st.number_input(
        "Valor de la inversión (COP)",
        min_value = 0,
        step      = 100_000,
        value     = 0,
        help      = "Lo provee el equipo técnico tras la visita de viabilidad.",
    )

with col_b:
    operador_red = st.selectbox(
        "Operador de Red",
        options = operadores_red(),
        index   = None,
        placeholder = "Selecciona un OR…",
    )

st.divider()

listo = bool(codigo_bia.strip()) and inversion > 0 and operador_red

if st.button("Generar simulación", type="primary", disabled=not listo):
    with st.status("Procesando simulación…", expanded=True) as status:
        try:
            loop = asyncio.get_event_loop()

            st.write("📡 Consultando Hubspot General por código Bia…")
            st.write("🧮 Aplicando lógica de la calculadora NT2…")
            st.write("📑 Copiando plantilla Slides y reemplazando placeholders…")
            st.write("📁 Subiendo PPTX al Shared Drive Nivel de Tensión…")
            st.write("📊 Actualizando Excel acumulado…")

            resultado = loop.run_until_complete(
                procesar_simulacion(codigo_bia.strip(), inversion, operador_red)
            )

            st.session_state["nt2_resultado"] = resultado
            st.session_state["nt2_codigo"]    = codigo_bia.strip()
            # Reseteamos el estado del borrador para esta nueva simulación
            st.session_state.pop("nt2_draft", None)

            status.update(label="¡Simulación lista!", state="complete")

        except ValueError as e:
            status.update(label="Error de validación", state="error")
            st.error(f"**{e}**")
        except Exception as e:
            status.update(label="Error al procesar", state="error")
            st.error(f"**Error:** {e}")
            st.exception(e)


# ---------------------------------------------------------------------------
# Resultado (persiste tras el rerun de Streamlit gracias a session_state)
# ---------------------------------------------------------------------------
if "nt2_resultado" in st.session_state:
    resultado = st.session_state["nt2_resultado"]
    cliente   = resultado["cliente"]
    sim       = resultado["simulacion"]
    codigo    = st.session_state.get("nt2_codigo", "")

    st.divider()
    st.subheader("Resumen")
    st.markdown(f"""
| Campo | Valor |
|---|---|
| Código Bia | {codigo} |
| Razón social | {cliente['razon_social']} |
| Dirección | {cliente['direccion']} |
| Ciudad | {cliente['ciudad']} |
| Operador de Red | {sim['operador_red']} |
| Energía | {cliente['energia']:,.0f} kWh |
| **Ahorro mensual** | **{formato_cop(sim['ahorro_mensual'])}** |
| **Inversión total** | **{formato_cop(sim['inversion'])}** |
| **Ahorro vida útil** | **{formato_cop(sim['vida_util'])}** |
| **ROI** | **{formato_meses(sim['roi_meses'])}** |
""")

    st.divider()

    col_drive, _ = st.columns([1, 2])
    with col_drive:
        st.link_button(
            "📂 Abrir Shared Drive",
            resultado["drive_url"],
            use_container_width=True,
        )

    st.subheader("📥 Descargas y envío")
    col_pdf, col_email, col_slides = st.columns(3)

    with col_pdf:
        st.download_button(
            label     = "📄 PDF",
            data      = resultado["pdf"],
            file_name = resultado["pdf_nombre"],
            mime      = "application/pdf",
            use_container_width=True,
        )
        st.caption(resultado["pdf_nombre"])

    with col_email:
        if gmail_autorizado():
            if st.button("✉️ Enviar vía email", use_container_width=True):
                with st.spinner("Creando borrador en Gmail…"):
                    try:
                        draft = crear_borrador_gmail(
                            razon_social = cliente["razon_social"],
                            pdf_bytes    = resultado["pdf"],
                            pdf_filename = resultado["pdf_nombre"],
                        )
                        st.session_state["nt2_draft"] = draft
                    except Exception as e:
                        st.error(f"No se pudo crear el borrador: {e}")

            if st.session_state.get("nt2_draft"):
                draft = st.session_state["nt2_draft"]
                st.success("✅ Borrador creado en Gmail")
                st.link_button(
                    "Abrir borradores en Gmail",
                    draft["url"],
                    use_container_width=True,
                )
            else:
                st.caption("Crea un borrador en Gmail con PDF adjunto")
        else:
            # Fallback: si todavía no se autorizó Gmail, ofrecer .eml descargable
            eml_bytes = generar_eml(
                razon_social  = cliente["razon_social"],
                pdf_bytes     = resultado["pdf"],
                pdf_filename  = resultado["pdf_nombre"],
            )
            st.download_button(
                label     = "✉️ Borrador (.eml)",
                data      = eml_bytes,
                file_name = f"Borrador - {cliente['razon_social'] or codigo}.eml",
                mime      = "message/rfc822",
                use_container_width=True,
            )
            st.caption("Gmail no autorizado. Corre `authorize_gmail.py` para activar el envío directo.")

    with col_slides:
        st.link_button(
            "🖼️ Editar PPTX",
            resultado["slides_url"],
            use_container_width=True,
        )
