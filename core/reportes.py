"""Reporte consolidado de un Atributo de Egreso: Excel (varias hojas) y PDF (resumen y tablas agregadas).

El formato es genérico: no sigue aún una cédula oficial de CACEI. Cuando se confirme el formato que
piden los organismos acreditadores, sólo hay que ajustar las hojas que se arman aquí.
"""
import io
from datetime import date

import pandas as pd
from openpyxl.styles import Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import db
from core.adopcion import niveles_encuestas
from core.resumen import metricas, resumen_preliminar
from core.rubricas import GRADOS_OFICIALES


def tablas(rubrica: dict) -> dict[str, pd.DataFrame]:
    """Hojas del reporte, como DataFrames listos para mostrar o exportar."""
    minimo = rubrica["nivel_minimo"]
    nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
    m = metricas(rubrica)

    adopcion = m["tabla"].drop(columns="fuente").copy()
    adopcion["Peso"] = adopcion["Peso"].round(2)
    adopcion["Nivel promedio"] = adopcion["Nivel promedio"].round(2)
    adopcion["Cumplimiento"] = adopcion["Cumplimiento"].round(3)

    df = db.dataframe(
        """SELECT a.matricula AS Matrícula, a.nombre AS Alumno, s.nombre AS "Unidad de aprendizaje", ev.indicador_id,
                  COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel, ev.revisado
           FROM evaluaciones ev JOIN evidencias e ON e.id = ev.evidencia_id
           JOIN alumnos a ON a.id = e.alumno_id JOIN asignaturas s ON s.id = e.asignatura_id
           WHERE s.ae_id = ?""",
        (rubrica["id"],),
    )
    out = {"Adopción por fuente": adopcion}
    if not df.empty:
        df["Indicador"] = df["indicador_id"].map(nombres)
        df["Cumple"] = df["nivel"] >= minimo
        df["Nivel"] = df["nivel"].astype(str).map(rubrica["niveles"])
        df["Revisado por docente"] = df["revisado"].map({1: "Sí", 0: "No"})
        por_alumno = df.pivot_table(index=["Matrícula", "Alumno"], columns="Indicador", values="nivel", aggfunc="mean").round(1)
        por_alumno["Promedio"] = por_alumno.mean(axis=1).round(2)
        por_alumno["Cumple AE"] = por_alumno["Promedio"] >= minimo
        out["Por alumno"] = por_alumno.reset_index()
        out["Por UA"] = df.groupby("Unidad de aprendizaje").agg(
            Evaluaciones=("nivel", "size"), **{"Nivel promedio": ("nivel", "mean"), "% cumplimiento": ("Cumple", "mean")}
        ).round(2).reset_index()
        out["Detalle"] = df[["Matrícula", "Alumno", "Unidad de aprendizaje", "Indicador", "Nivel", "Cumple", "Revisado por docente"]]

    enc = niveles_encuestas(rubrica)
    if not enc.empty:
        enc = enc.groupby("tipo").agg(
            Respuestas=("nivel", "size"), Promedio=("valoracion", "mean"), **{"Nivel promedio": ("nivel", "mean")},
            Cumplimiento=("nivel", lambda n: (n >= minimo).mean()),
        ).round(3).reset_index().rename(columns={"tipo": "Tipo"})
        out["Encuestas"] = enc
    out["Bitácora de cargas"] = db.dataframe(
        "SELECT datetime(fecha, 'localtime') AS Fecha, fuente AS Fuente, archivo AS Archivo, filas AS Filas, "
        "aceptadas AS Aceptadas, rechazadas AS Rechazadas, omitidas AS Omitidas FROM cargas ORDER BY id"
    )
    return out


def libro_excel(rubrica: dict) -> bytes:
    """Libro .xlsx con la hoja Resumen (texto preliminar y estado de validación) y las hojas de `tablas()`."""
    resumen = resumen_preliminar(rubrica).replace("**", "")
    validacion = rubrica.get("validacion", {})
    portada = pd.DataFrame(
        {
            "Concepto": ["Atributo de Egreso", "Programa", "Fecha de generación", "Nivel mínimo de cumplimiento",
                         "Validación de la rúbrica", "Resumen preliminar"],
            "Valor": [f"{rubrica['id']} · {rubrica['nombre']}", rubrica["programa"], date.today().isoformat(),
                      rubrica["nivel_minimo"], validacion.get("estado", "pendiente"), resumen],
        }
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as xlsx:
        portada.to_excel(xlsx, sheet_name="Resumen", index=False)
        for nombre, tabla in tablas(rubrica).items():
            tabla.to_excel(xlsx, sheet_name=nombre[:31], index=False)
        for hoja in xlsx.book.worksheets:
            for col in hoja.columns:
                ancho = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                hoja.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 90 if hoja.title == "Resumen" else 40)
        resumen_hoja = xlsx.book["Resumen"]
        for fila in resumen_hoja.iter_rows(min_row=2):
            for c in fila:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    return buffer.getvalue()


def _celda(valor) -> str:
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if pd.isna(valor):
        return "—"
    return f"{valor:g}" if isinstance(valor, float) else str(valor)


def pdf(rubrica: dict) -> bytes:
    """Reporte en PDF (horizontal) con el resumen y las tablas agregadas; el detalle por evaluación queda en el Excel."""
    estilos = getSampleStyleSheet()
    validacion = rubrica.get("validacion", {}).get("estado", "pendiente")
    historia = [
        Paragraph(f"{rubrica['id']} · {rubrica['nombre']}", estilos["Title"]),
        Paragraph(f"{rubrica['programa']} · generado el {date.today().isoformat()} · validación de la rúbrica: {validacion}", estilos["Normal"]),
        Spacer(1, 10),
        Paragraph("Resumen preliminar", estilos["Heading2"]),
    ]
    # Helvetica (fuente base del PDF) no incluye ≤ ni ≥.
    historia += [Paragraph(p, estilos["Normal"]) for p in resumen_preliminar(rubrica).replace("**", "").replace("≤", "<=").replace("≥", ">=").split("\n\n")]

    for nombre, tabla in tablas(rubrica).items():
        if nombre in ("Detalle", "Bitácora de cargas"):
            continue
        datos = [list(map(str, tabla.columns))] + [[_celda(v) for v in fila] for fila in tabla.itertuples(index=False)]
        t = Table(datos, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ]))
        historia += [Spacer(1, 10), Paragraph(nombre, estilos["Heading2"]), t]

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=landscape(A4), title=f"Reporte {rubrica['id']}").build(historia)
    return buffer.getvalue()


# --- Cédula "Valoración de atributo de egreso en unidad de aprendizaje" (formato PG-CFP-01-RC01) ---
# La evaluación se hace en 4 niveles; el formato oficial sólo admite NS / SA / SO, así que se
# convierte con la equivalencia de la rúbrica (`formato_oficial.equivalencia`).

GRADOS = GRADOS_OFICIALES
GRADOS_NOMBRE = {"NS": "No Satisfactorio", "SA": "Satisfactorio", "SO": "Sobresaliente"}


def equivalencia(rubrica: dict) -> dict[int, str]:
    """Nivel (1-4) -> grado oficial. Sin equivalencia explícita: bajo el mínimo es NS, el último nivel SO y el resto SA."""
    eq = rubrica.get("formato_oficial", {}).get("equivalencia")
    if eq:
        return {int(k): v for k, v in eq.items()}
    minimo = rubrica["nivel_minimo"]
    return {n: "NS" if n < minimo else "SO" if n == 4 else "SA" for n in (1, 2, 3, 4)}


def niveles_por_alumno(rubrica: dict, asignatura: str) -> pd.DataFrame:
    """Nivel (1-4) de cada alumno por indicador en una unidad de aprendizaje; con varias evidencias se promedia y redondea."""
    df = db.dataframe(
        """SELECT a.matricula AS Matrícula, a.nombre AS Alumno, ev.indicador_id,
                  COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel
           FROM evaluaciones ev JOIN evidencias e ON e.id = ev.evidencia_id
           JOIN alumnos a ON a.id = e.alumno_id JOIN asignaturas s ON s.id = e.asignatura_id
           WHERE s.ae_id = ? AND s.nombre = ?""",
        (rubrica["id"], asignatura),
    )
    if df.empty:
        return pd.DataFrame()
    tabla = df.pivot_table(index=["Matrícula", "Alumno"], columns="indicador_id", values="nivel", aggfunc="mean")
    return (tabla + 0.5).apply(lambda col: col.map(lambda x: int(x) if pd.notna(x) else pd.NA)).reset_index()


def cedula_ua(rubrica: dict, asignatura: str) -> dict[str, pd.DataFrame]:
    """Tablas de la cédula: 'Distribución' (% y cantidad por grado), 'Descriptores' y 'Desglose' (una X por grado y alumno)."""
    eq = equivalencia(rubrica)
    ids = [i["id"] for i in rubrica["indicadores"]]
    por_alumno = niveles_por_alumno(rubrica, asignatura)
    if por_alumno.empty:
        return {}

    distribucion, desglose = [], por_alumno[["Matrícula", "Alumno"]].copy()
    for ind in rubrica["indicadores"]:
        grados = por_alumno[ind["id"]].map(lambda n: eq[n] if pd.notna(n) else None)
        total = grados.notna().sum()
        fila = {"Indicador": f"{ind['id']} {ind['nombre']}", "Evaluados": int(total)}
        for g in GRADOS:
            n = int((grados == g).sum())
            fila[g] = f"{n / total:.1%} ({n})" if total else "—"
            desglose[f"{ind['id']} {g}"] = (grados == g).map({True: "X", False: ""})
        distribucion.append(fila)

    descriptores = pd.DataFrame(
        [{"Indicador": i["id"], **{f"{n} · {rubrica['niveles'][str(n)]} ({eq[n]})": i["niveles"][str(n)] for n in (1, 2, 3, 4)}}
         for i in rubrica["indicadores"]]
    )
    return {"Distribución": pd.DataFrame(distribucion), "Descriptores": descriptores, "Desglose": desglose}


def cedula_pdf(rubrica: dict, asignatura: str, datos: dict) -> bytes:
    """Cédula en PDF. `datos`: institucion (líneas), clave, grupo, periodo, actividad, elaboro, reviso (todos opcionales)."""
    estilos = getSampleStyleSheet()
    chico = estilos["Normal"].clone("chico", fontSize=8, leading=10)
    centro = estilos["Normal"].clone("centro", alignment=1)
    tablas_ = cedula_ua(rubrica, asignatura)
    codigo = rubrica.get("formato_oficial", {}).get("codigo", "")
    ids = [i["id"] for i in rubrica["indicadores"]]

    def tabla(filas, anchos=None, encabezados=1, fuente=8):
        t = Table(filas, colWidths=anchos, repeatRows=encabezados)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), fuente),
            ("BACKGROUND", (0, 0), (-1, encabezados - 1), colors.HexColor("#e2e8f0")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def parrafos(filas):
        return [[Paragraph(str(c), chico) for c in fila] for fila in filas]

    historia = [Paragraph(l, centro) for l in datos.get("institucion", "").splitlines() if l.strip()]
    historia += [Spacer(1, 6), Paragraph("<b>Valoración de atributo de egreso en unidad de aprendizaje</b>", centro), Spacer(1, 10)]
    criterios = "<br/>".join(f"{i['id']} {i['descripcion']}" for i in rubrica["indicadores"])
    historia.append(tabla(parrafos([
        ["Programa Educativo", rubrica["programa"], "Periodo", datos.get("periodo", "")],
        ["Clave de la unidad", datos.get("clave", ""), "Nombre de la unidad", asignatura],
        ["Grupo", datos.get("grupo", ""), "Atributo de egreso", f"{rubrica['id']} · {rubrica['nombre']}: {rubrica['descripcion']}"],
        ["Indicadores", criterios, "", ""],
    ]), anchos=[90, 200, 90, 380]))

    if tablas_:
        dist = tablas_["Distribución"]
        historia += [Spacer(1, 10), Paragraph("Porcentaje y cantidad de alumnos evaluados por grado de cumplimiento", estilos["Heading4"])]
        encabezado = ["Indicador", "Evaluados"] + [f"{GRADOS_NOMBRE[g]} ({g})" for g in GRADOS]
        historia.append(tabla(parrafos([encabezado] + dist.values.tolist()), anchos=[330, 60, 130, 130, 130]))

        desc = tablas_["Descriptores"]
        historia += [Spacer(1, 10), Paragraph("Descripción de los niveles de cumplimiento (NS = niveles 1-2, SA = 3, SO = 4, según la equivalencia de la rúbrica)", estilos["Heading4"])]
        historia.append(tabla(parrafos([list(desc.columns)] + desc.values.tolist()), anchos=[58, 170, 170, 170, 170]))

        historia += [Spacer(1, 10), Paragraph("Desglose por alumno", estilos["Heading4"])]
        d = tablas_["Desglose"]
        cab1 = ["Matrícula", "Alumno"] + [x for i in ids for x in (i, "", "")]
        cab2 = ["", ""] + list(GRADOS) * len(ids)
        t = tabla([cab1, cab2] + d.values.tolist(), anchos=[60, 190] + [34] * (3 * len(ids)), encabezados=2)
        t.setStyle(TableStyle([("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1))] +
                              [("SPAN", (2 + 3 * k, 0), (4 + 3 * k, 0)) for k in range(len(ids))] +
                              [("ALIGN", (2, 0), (-1, -1), "CENTER")]))
        historia.append(t)
    else:
        historia.append(Paragraph("No hay evaluaciones registradas para esta unidad de aprendizaje.", estilos["Normal"]))

    historia += [Spacer(1, 10), Paragraph("Descripción de la actividad realizada", estilos["Heading4"]),
                 Paragraph((datos.get("actividad") or "—").replace("\n", "<br/>"), estilos["Normal"]), Spacer(1, 16),
                 tabla([["Elaboró", "Revisó"], [datos.get("elaboro", ""), datos.get("reviso", "")]], anchos=[250, 250], fuente=9)]

    def pie(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(doc.pagesize[0] - 36, 20, f"{codigo} · generado el {date.today().isoformat()}")

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=landscape(A4), title=f"Cédula {rubrica['id']} · {asignatura}").build(historia, onFirstPage=pie, onLaterPages=pie)
    return buffer.getvalue()
