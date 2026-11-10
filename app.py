"""Punto de entrada: `streamlit run app.py`. Define las páginas en el orden del flujo de trabajo."""
import streamlit as st

st.set_page_config(page_title="EduVisual", page_icon="📊", layout="wide")

st.navigation([
    st.Page("paginas/inicio.py", title="Inicio", icon=":material/home:", default=True),
    st.Page("paginas/carga_de_datos.py", title="Carga de datos", icon=":material/upload_file:"),
    st.Page("paginas/evaluar_egresado.py", title="Evaluar egresado", icon=":material/fact_check:"),
    st.Page("paginas/panel.py", title="Panel", icon=":material/monitoring:"),
    st.Page("paginas/reportes.py", title="Reportes", icon=":material/description:"),
]).run()
