import altair as alt
import streamlit as st

from core import db
from core.adopcion import resumen_adopcion
from core.ui import iniciar, rubrica_activa

iniciar("Panel de resultados")
rubrica = rubrica_activa()
minimo = rubrica["nivel_minimo"]
nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}

st.subheader("Adopción del Atributo de Egreso por fuente")
tabla, indice = resumen_adopcion(rubrica)
cols = st.columns(len(tabla) + 1)
cols[0].metric(
    "Índice de adopción",
    f"{indice:.0%}" if indice is not None else "—",
    help="Promedio ponderado del cumplimiento de cada fuente con datos (pesos definidos en la rúbrica).",
)
for col, fila in zip(cols[1:], tabla.to_dict("records")):
    col.metric(
        f"{fila['Fuente']} · peso {fila['Peso']:.0%}",
        f"{fila['Cumplimiento']:.0%}" if fila["Registros"] else "Sin datos",
        help=f"{fila['Registros']} registros de {fila['Alumnos']} alumnos con nivel ≥ {minimo}.",
    )
con_datos = tabla[tabla["Registros"] > 0]
if not con_datos.empty:
    st.altair_chart(
        alt.Chart(con_datos).mark_bar().encode(
            x=alt.X("Cumplimiento:Q", title=f"% con nivel ≥ {minimo}", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("Fuente:N", title=None, sort=None),
            tooltip=["Fuente", alt.Tooltip("Cumplimiento:Q", format=".0%"), "Registros", alt.Tooltip("Nivel promedio:Q", format=".2f")],
        ).properties(height=140),
        width="stretch",
    )
st.caption("Las calificaciones y los resultados CENEVAL se cargan en la página «Carga de datos».")

st.divider()
st.subheader("Evidencias evaluadas con la rúbrica")

df = db.dataframe(
    """
    SELECT a.nombre AS alumno, s.nombre AS asignatura, ev.indicador_id,
           ev.nivel_sugerido, ev.nivel_final, ev.revisado,
           COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel
    FROM evaluaciones ev
    JOIN evidencias e ON e.id = ev.evidencia_id
    JOIN alumnos a ON a.id = e.alumno_id
    JOIN asignaturas s ON s.id = e.asignatura_id
    """
)
if df.empty:
    st.info("No hay evaluaciones todavía. Carga los datos de ejemplo desde la página principal.")
    st.stop()

solo_revisadas = st.checkbox("Contar solo evaluaciones revisadas por el docente")
if solo_revisadas:
    df = df[df["revisado"] == 1]
    if df.empty:
        st.info("Aún no hay evaluaciones revisadas.")
        st.stop()

df["indicador"] = df["indicador_id"].map(nombres)
df["cumple"] = df["nivel"] >= minimo

revisadas = df[df["revisado"] == 1]
c1, c2, c3 = st.columns(3)
c1.metric(f"Cumplimiento (nivel ≥ {minimo})", f"{df['cumple'].mean():.0%}")
c2.metric("Nivel promedio", f"{df['nivel'].mean():.2f}")
c3.metric(
    "Concordancia motor-docente",
    f"{(revisadas['nivel_final'] == revisadas['nivel_sugerido']).mean():.0%}" if not revisadas.empty else "—",
    help="Porcentaje de evaluaciones revisadas donde el docente dejó el nivel sugerido por el motor.",
)

st.subheader("Cumplimiento por indicador")
por_indicador = df.groupby("indicador", as_index=False)["cumple"].mean()
st.altair_chart(
    alt.Chart(por_indicador).mark_bar().encode(
        x=alt.X("indicador:N", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("cumple:Q", title="% con nivel satisfactorio", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        tooltip=["indicador", alt.Tooltip("cumple:Q", format=".0%")],
    ),
    width="stretch",
)

st.subheader("Distribución de niveles por asignatura")
distribucion = df.groupby(["asignatura", "nivel"], as_index=False).size()
st.altair_chart(
    alt.Chart(distribucion).mark_bar().encode(
        x=alt.X("asignatura:N", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("size:Q", title="Evaluaciones", stack="normalize", axis=alt.Axis(format="%")),
        color=alt.Color("nivel:O", title="Nivel", scale=alt.Scale(scheme="blues")),
        tooltip=["asignatura", "nivel", "size"],
    ),
    width="stretch",
)

st.subheader("Detalle por alumno")
tabla = df.pivot_table(index=["alumno", "asignatura"], columns="indicador_id", values="nivel", aggfunc="mean").round(1)
tabla["promedio"] = tabla.mean(axis=1).round(2)
st.dataframe(tabla, width="stretch")
