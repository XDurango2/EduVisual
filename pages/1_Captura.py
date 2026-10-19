import streamlit as st

from core import db
from core.evaluador import evaluar
from core.extraccion import texto_de_archivo
from core.ui import iniciar, rubrica_activa

iniciar("Captura de evidencias")
rubrica = rubrica_activa()

alumnos = db.consulta("SELECT id, matricula, nombre FROM alumnos ORDER BY nombre")
asignaturas = db.consulta("SELECT id, nombre FROM asignaturas ORDER BY nombre")

if not asignaturas:
    st.info("No hay datos todavía. Carga los datos de ejemplo desde la página principal.")
    st.stop()

col1, col2 = st.columns(2)
alumno = col1.selectbox("Alumno", alumnos, format_func=lambda a: f"{a['matricula']} · {a['nombre']}")
asignatura = col2.selectbox("Asignatura", asignaturas, format_func=lambda a: a["nombre"])

archivo = st.file_uploader("Evidencia (TXT, MD, y PDF/DOCX si están instaladas las librerías)", type=["txt", "md", "pdf", "docx"])
texto_manual = st.text_area("...o pega el texto de la evidencia", height=200)

if st.button("Guardar y evaluar", type="primary"):
    try:
        if archivo:
            nombre, texto = archivo.name, texto_de_archivo(archivo.name, archivo.getvalue())
        else:
            nombre, texto = "texto_pegado.txt", texto_manual
    except ValueError as e:
        st.error(str(e))
        st.stop()

    if not texto.strip():
        st.error("La evidencia está vacía.")
        st.stop()

    with st.spinner("Evaluando evidencia..."):
        evidencia_id = db.guardar_evidencia(alumno["id"], asignatura["id"], nombre, texto)
        resultados, aviso = evaluar(texto, rubrica)
        for r in resultados:
            db.guardar_evaluacion(evidencia_id, r)

    if aviso:
        st.warning(aviso)
    st.success("Evidencia evaluada. Revisa la sugerencia en la página de Revisión.")
    nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
    for r in resultados:
        st.markdown(f"**{nombres[r['indicador_id']]}** → nivel {r['nivel']} · {rubrica['niveles'][str(r['nivel'])]}  \n_{r['justificacion']}_")
