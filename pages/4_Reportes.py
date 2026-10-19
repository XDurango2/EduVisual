import streamlit as st

from core import db
from core.ui import iniciar, rubrica_activa

iniciar("Reportes")
rubrica = rubrica_activa()
minimo = rubrica["nivel_minimo"]
nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}

df = db.dataframe(
    """
    SELECT a.matricula AS Matrícula, a.nombre AS Alumno, s.nombre AS Asignatura, ev.indicador_id,
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

st.subheader("Por alumno")
por_alumno = df.pivot_table(index=["Matrícula", "Alumno"], columns="Indicador", values="nivel", aggfunc="mean").round(1)
por_alumno["Promedio"] = por_alumno.mean(axis=1).round(2)
por_alumno["Cumple AE"] = por_alumno["Promedio"] >= minimo
st.dataframe(por_alumno, width="stretch")

st.subheader("Por asignatura")
por_asignatura = df.groupby("Asignatura").agg(
    Evaluaciones=("nivel", "size"), **{"Nivel promedio": ("nivel", "mean"), "% cumplimiento": ("Cumple", "mean")}
).round(2)
st.dataframe(por_asignatura, width="stretch")

st.subheader("Programa educativo")
st.metric("Cumplimiento global del AE", f"{df['Cumple'].mean():.0%}")

st.subheader("Exportar")
detalle = df[["Matrícula", "Alumno", "Asignatura", "Indicador", "Nivel", "Cumple", "Revisado por docente"]]
c1, c2, c3 = st.columns(3)
# utf-8-sig para que Excel abra bien los acentos.
c1.download_button("Detalle (CSV)", detalle.to_csv(index=False).encode("utf-8-sig"), "ae_detalle.csv", "text/csv")
c2.download_button("Por alumno (CSV)", por_alumno.reset_index().to_csv(index=False).encode("utf-8-sig"), "ae_por_alumno.csv", "text/csv")
c3.download_button("Por asignatura (CSV)", por_asignatura.reset_index().to_csv(index=False).encode("utf-8-sig"), "ae_por_asignatura.csv", "text/csv")
