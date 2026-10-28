"""Resumen preliminar del Atributo de Egreso, redactado con reglas a partir de las métricas.

No usa el LLM: cada afirmación sale de un número calculado, así que es reproducible y auditable.
Es un borrador para el docente o el comité, no un dictamen.
"""
from core import db
from core.adopcion import niveles_encuestas, resumen_adopcion


def metricas(rubrica: dict) -> dict:
    """Números base del resumen y del reporte consolidado."""
    minimo = rubrica["nivel_minimo"]
    tabla, indice = resumen_adopcion(rubrica)

    ev = db.dataframe(
        """SELECT ev.indicador_id, ev.nivel_sugerido, ev.nivel_final, ev.revisado,
                  COALESCE(ev.nivel_final, ev.nivel_sugerido) AS nivel
           FROM evaluaciones ev JOIN evidencias e ON e.id = ev.evidencia_id
           JOIN asignaturas s ON s.id = e.asignatura_id WHERE s.ae_id = ?""",
        (rubrica["id"],),
    )
    por_indicador = {}
    if not ev.empty:
        por_indicador = (ev.assign(cumple=ev["nivel"] >= minimo).groupby("indicador_id")["cumple"].mean()).to_dict()
    revisadas = ev[ev["revisado"] == 1]
    concordancia = (revisadas["nivel_final"] == revisadas["nivel_sugerido"]).mean() if len(revisadas) else None

    enc = niveles_encuestas(rubrica)
    comentarios = enc[enc["comentario"] != ""].to_dict("records")
    return {
        "tabla": tabla, "indice": indice, "minimo": minimo, "evaluaciones": len(ev), "revisadas": len(revisadas),
        "concordancia": concordancia, "por_indicador": por_indicador, "comentarios": comentarios,
    }


def resumen_preliminar(rubrica: dict, m: dict | None = None) -> str:
    m = m or metricas(rubrica)
    nombres = {i["id"]: i["nombre"] for i in rubrica["indicadores"]}
    if m["indice"] is None:
        return "Aún no hay datos suficientes para generar un resumen."

    lineas = [f"**{rubrica['id']} · {rubrica['nombre']}** — índice de adopción combinado: **{m['indice']:.0%}**."]

    con_datos = m["tabla"][m["tabla"]["Registros"] > 0].sort_values("Cumplimiento")
    sin_datos = m["tabla"][m["tabla"]["Registros"] == 0]
    bajo, alto = con_datos.iloc[0], con_datos.iloc[-1]
    if len(con_datos) > 1:
        lineas.append(
            f"La fuente con mayor cumplimiento es {alto['Fuente']} ({alto['Cumplimiento']:.0%}) y la menor es "
            f"{bajo['Fuente']} ({bajo['Cumplimiento']:.0%}), con cumplimiento = nivel ≥ {m['minimo']}."
        )
    if not sin_datos.empty:
        lineas.append("Faltan datos de: " + ", ".join(sin_datos["Fuente"]) + "; el índice se calculó sin ellas.")

    if m["por_indicador"]:
        ind_bajo = min(m["por_indicador"], key=m["por_indicador"].get)
        lineas.append(
            f"El indicador más débil en evidencias es «{nombres.get(ind_bajo, ind_bajo)}» "
            f"({m['por_indicador'][ind_bajo]:.0%} con nivel satisfactorio)."
        )
    if m["evaluaciones"]:
        pendientes = m["evaluaciones"] - m["revisadas"]
        texto = f"El docente ha revisado {m['revisadas']} de {m['evaluaciones']} evaluaciones"
        if m["concordancia"] is not None:
            texto += f"; en las revisadas coincide con el motor el {m['concordancia']:.0%}"
        lineas.append(texto + (f". Quedan {pendientes} pendientes de revisión." if pendientes else "."))

    if m["comentarios"]:
        criticos = [c for c in m["comentarios"] if c["nivel"] < m["minimo"]]
        lineas.append(f"Las encuestas incluyen {len(m['comentarios'])} comentarios, {len(criticos)} de ellos con nivel por debajo del mínimo.")

    estado = rubrica.get("validacion", {}).get("estado", "pendiente")
    if estado != "validada":
        lineas.append(f"La rúbrica aún no está validada académicamente (estado: {estado}); tómese como resultado preliminar.")
    return "\n\n".join(lineas)
