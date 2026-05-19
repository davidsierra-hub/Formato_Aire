import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Cumplimiento AIR-E",
    page_icon="⚡",
    layout="centered",
)

pg = st.navigation([
    st.Page("pages/Generador_Carpetas.py", title="Generador Carpetas AIR-E", icon="⚡"),
    st.Page("pages/Medidores_Directa.py",  title="Medidores Directa",        icon="📡"),
])
pg.run()
