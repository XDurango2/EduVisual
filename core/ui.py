import streamlit as st

from core import db
from core.evaluador import estado_motor
from core.rubricas import cargar_rubricas, errores_rubricas


def iniciar(titulo: str):
    """Configuración común de cada página: título, base de datos y estado del motor en la barra lateral."""
    st.set_page_config(page_title=f"EduVisual - {titulo}", page_icon="📊", layout="wide")
    db.init_db()
    motor, detalle = estado_motor()
    with st.sidebar:
        st.caption("Motor de evaluación")
        (st.success if motor == "ollama" else st.warning)(detalle)
        for archivo, errores in errores_rubricas().items():
            st.error(f"Rúbrica inválida ({archivo}): " + "; ".join(errores))
    st.title(titulo)


def rubrica_activa() -> dict:
    rubricas = cargar_rubricas()
    if not rubricas:
        st.error("No hay rúbricas válidas en data/rubricas. Revisa los errores en la barra lateral.")
        st.stop()
    return rubricas[next(iter(rubricas))]
