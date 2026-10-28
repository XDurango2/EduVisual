import streamlit as st

from core import db, reportes
from core.reportes import libro_excel, pdf
from core.resumen import resumen_preliminar
from core.ui import iniciar, rubrica_activa

iniciar("Reportes")
rubrica = rubrica_activa()
minimo = rubrica["nivel_minimo"]
nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}

df = db.dataframe(
    """
    SELECT a.matricula AS Matrícula, a.nombre AS Alumno, s.nombre AS "Unidad de aprendizaje", ev.indicador_id,
           COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel, ev.revisado
    FROM evaluaciones ev
    JOIN evidencias e ON e.id = ev.evidencia_id
    JOIN alumnos a ON a.id = e.alumno_id
    JOIN asignaturas s ON s.id = e.asignatura_id
    """
)
if df.empty:
    st.info("No hay evaluaciones para reportar.")
    st.stop()

df["Indicador"] = df["indicador_id"].map(nombres)
df["Cumple"] = df["nivel"] >= minimo
etiqueta = {k: v for k, v in rubrica["niveles"].items()}
df["Nivel"] = df["nivel"].astype(str).map(etiqueta)
df["Revisado por docente"] = df["revisado"].map({1: "Sí", 0: "No"})

st.caption(f"{rubrica['id']} · {rubrica['nombre']} · cumple con nivel ≥ {minimo}")

st.subheader("Reporte consolidado")
st.markdown(resumen_preliminar(rubrica))
b1, b2 = st.columns(2)
b1.download_button(
    "Descargar reporte consolidado (Excel)", libro_excel(rubrica), f"reporte_{rubrica['id']}.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
)
b2.download_button("Descargar reporte (PDF)", pdf(rubrica), f"reporte_{rubrica['id']}.pdf", "application/pdf")
st.caption(
    "El Excel incluye resumen preliminar, adopción por fuente, resultados por alumno, unidad de aprendizaje y detalle, encuestas y bitácora de cargas; "
    "el PDF trae el resumen y las tablas agregadas. "
    "El formato es genérico: aún no sigue una cédula oficial de CACEI."
)

st.subheader("Por alumno")
por_alumno = df.pivot_table(index=["Matrícula", "Alumno"], columns="Indicador", values="nivel", aggfunc="mean").round(1)
por_alumno["Promedio"] = por_alumno.mean(axis=1).round(2)
por_alumno["Cumple AE"] = por_alumno["Promedio"] >= minimo
st.dataframe(por_alumno, width="stretch")

st.subheader("Por unidad de aprendizaje")
por_asignatura = df.groupby("Unidad de aprendizaje").agg(
    Evaluaciones=("nivel", "size"), **{"Nivel promedio": ("nivel", "mean"), "% cumplimiento": ("Cumple", "mean")}
).round(2)
st.dataframe(por_asignatura, width="stretch")

st.subheader("Programa educativo")
st.metric("Cumplimiento global del AE", f"{df['Cumple'].mean():.0%}")

st.subheader("Exportar")
detalle = df[["Matrícula", "Alumno", "Unidad de aprendizaje", "Indicador", "Nivel", "Cumple", "Revisado por docente"]]
c1, c2, c3 = st.columns(3)
# utf-8-sig para que Excel abra bien los acentos.
c1.download_button("Detalle (CSV)", detalle.to_csv(index=False).encode("utf-8-sig"), "ae_detalle.csv", "text/csv")
c2.download_button("Por alumno (CSV)", por_alumno.reset_index().to_csv(index=False).encode("utf-8-sig"), "ae_por_alumno.csv", "text/csv")
c3.download_button("Por UA (CSV)", por_asignatura.reset_index().to_csv(index=False).encode("utf-8-sig"), "ae_por_asignatura.csv", "text/csv")

st.subheader("Cédula oficial por unidad de aprendizaje")
st.caption("Formato de valoración de atributo de egreso: los 4 niveles se agrupan en NS / SA / SO con la equivalencia de la rúbrica.")
asignatura = st.selectbox("Unidad de aprendizaje", sorted(df["Asignatura"].unique()))
cedula = reportes.cedula_ua(rubrica, asignatura)
eq = reportes.equivalencia(rubrica)
st.caption("Equivalencia: " + " · ".join(f"{rubrica['niveles'][str(n)]} → {g}" for n, g in eq.items()))
st.dataframe(cedula["Distribución"], width="stretch", hide_index=True)
with st.expander("Desglose por alumno"):
    st.dataframe(cedula["Desglose"], width="stretch", hide_index=True)

with st.expander("Datos del formato y descarga"):
    c1, c2, c3 = st.columns(3)
    datos = {
        "institucion": st.text_area("Encabezado (una línea por renglón)", height=100),
        "clave": c1.text_input("Clave de la unidad"),
        "grupo": c2.text_input("Grupo"),
        "periodo": c3.text_input("Periodo"),
        "elaboro": c1.text_input("Elaboró"),
        "reviso": c2.text_input("Revisó"),
        "actividad": st.text_area("Descripción de la actividad realizada"),
    }
    st.download_button("Cédula (PDF)", reportes.cedula_pdf(rubrica, asignatura, datos), f"cedula_{rubrica['id']}.pdf", "application/pdf")
