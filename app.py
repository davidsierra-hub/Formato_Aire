import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="BIA Automatizaciones",
    page_icon="⚡",
    layout="centered",
)

pg = st.navigation([
    st.Page("pages/Generador_Carpetas.py",    title="Generador Carpetas AIR-E", icon="⚡"),
    st.Page("pages/Medidores_Directa.py",     title="Medidores Directa",        icon="📡"),
    st.Page("pages/Cambio_Nivel_Tension.py",  title="Cambio Nivel Tensión",     icon="🔌"),
    st.Page("pages/Cumplimiento_ESSA.py",     title="Generador Carpetas ESSA",  icon="🏢"),
    st.Page("pages/Kick_off.py",              title="Kick-off",                 icon="🤝"),
])
pg.run()
