"""Datos de ejemplo sintéticos para la rúbrica AE-03: alumnos, asignaturas, evidencias,
calificaciones, resultados CENEVAL y encuestas a empleadores. No contiene datos personales reales.

Uso: python -m core.seed
"""
import random
from pathlib import Path

import pandas as pd

from core import db, importacion
from core.evaluador import evaluar
from core.rubricas import cargar_rubricas

EJEMPLOS_DIR = Path(__file__).resolve().parent.parent / "data" / "ejemplos"
AE_ID = "AE-03"

ALUMNOS = [
    ("A0101", "Ana Torres"),
    ("A0102", "Luis Ramírez"),
    ("A0103", "María Soto"),
    ("A0104", "Diego Herrera"),
    ("A0105", "Sofía Medina"),
    ("A0106", "Carlos Núñez"),
    ("A0107", "Valeria Ortiz"),
    ("A0108", "Jorge Castillo"),
]
ASIGNATURAS = ["Ingeniería de Software", "Proyecto Integrador"]

# Fragmentos por indicador y nivel (1-4), escritos para ser coherentes con la rúbrica.
FRAGMENTOS = {
    "I1": {
        1: "El proyecto trata de hacer una aplicación que sirva para la escuela.",
        2: "El problema es que la gestión de inventarios es lenta y el objetivo es mejorarla.",
        3: "El problema consiste en el control manual de inventarios. Se levantaron las necesidades de los usuarios y se definió un alcance inicial.",
        4: "El problema consiste en el control manual de inventarios. Se levantaron las necesidades de los usuarios mediante entrevistas, se documentaron los requisitos funcionales y las restricciones de presupuesto, y se definió el alcance y el objetivo con especificaciones medibles.",
    },
    "I2": {
        1: "Se decidió usar la tecnología que ya conocía el equipo.",
        2: "Se consideraron otras alternativas pero se eligió la más sencilla.",
        3: "Se plantearon tres alternativas y se hizo una comparación considerando ventajas y desventajas de cada una.",
        4: "Se plantearon tres alternativas y se definieron criterios ponderados de evaluación. La matriz de decisión permitió la comparación de ventajas y desventajas, y la selección final quedó con justificación técnica.",
    },
    "I3": {
        1: "El sistema quedó terminado y funciona.",
        2: "Se hicieron algunas pruebas al final del semestre.",
        3: "Se realizaron pruebas con usuarios reales y se registraron los resultados, identificando algunas áreas de mejora.",
        4: "Se diseñó un plan de pruebas con métricas de desempeño y la validación de resultados con usuarios reales. Se analizó el impacto en la operación, los riesgos de seguridad y las acciones de mejora.",
    },
}
TITULOS = {"I1": "1. Planteamiento del problema", "I2": "2. Alternativas de solución", "I3": "3. Validación y resultados"}


def _redactar(asignatura: str, alumno: str, niveles: dict[str, int]) -> str:
    partes = [f"Reporte de proyecto - {asignatura}", f"Alumno: {alumno}", ""]
    for ind_id, nivel in niveles.items():
        partes += [TITULOS[ind_id], FRAGMENTOS[ind_id][nivel], ""]
    return "\n".join(partes)


def sembrar(reiniciar: bool = True, semilla: int = 42) -> dict:
    rng = random.Random(semilla)
    rubrica = cargar_rubricas()[AE_ID]
    if reiniciar:
        db.vaciar()
    else:
        db.init_db()

    EJEMPLOS_DIR.mkdir(parents=True, exist_ok=True)
    asignatura_ids = [db.obtener_o_crear_asignatura(n, AE_ID) for n in ASIGNATURAS]
    evidencias = 0
    habilidades = {}

    for matricula, nombre in ALUMNOS:
        alumno_id = db.obtener_o_crear_alumno(matricula, nombre)
        habilidad = rng.uniform(1.4, 3.9)
        habilidades[matricula] = habilidad
        for asig_id, asig in zip(asignatura_ids, ASIGNATURAS):
            bono = 0.4 if asig == "Proyecto Integrador" else 0.0
            niveles = {
                i["id"]: min(max(round(habilidad + bono + rng.uniform(-0.7, 0.7)), 1), 4)
                for i in rubrica["indicadores"]
            }
            texto = _redactar(asig, nombre, niveles)
            archivo = f"{matricula}_{asig.lower().replace(' ', '_')}.txt"
            (EJEMPLOS_DIR / archivo).write_text(texto, encoding="utf-8")

            evidencia_id = db.guardar_evidencia(alumno_id, asig_id, archivo, texto)
            resultados, _ = evaluar(texto, rubrica)
            for r in resultados:
                db.guardar_evaluacion(evidencia_id, r)
            evidencias += 1

            # Simula la revisión de un docente en ~60 % de las evidencias, con algunas correcciones.
            if rng.random() < 0.6:
                for fila in db.consulta("SELECT id, nivel_sugerido FROM evaluaciones WHERE evidencia_id = ?", (evidencia_id,)):
                    ajuste = rng.choice([0, 0, 0, 1, -1])
                    db.guardar_revision(fila["id"], min(max(fila["nivel_sugerido"] + ajuste, 1), 4))

    cargas = _sembrar_fuentes(rng, habilidades, rubrica)
    return {"alumnos": len(ALUMNOS), "asignaturas": len(ASIGNATURAS), "evidencias": evidencias, **cargas}


PERIODO = "2026-1"
EMPLEADORES = [
    "Empresa Software Ejemplo A",
    "Empresa Software Ejemplo B",
    "Consultoría TI Ejemplo",
    "Manufactura Ejemplo",
    "Gobierno Digital Ejemplo",
    "Startup Ejemplo",
]


def _sembrar_fuentes(rng: random.Random, habilidades: dict[str, float], rubrica: dict) -> dict:
    """Genera calificaciones, resultados CENEVAL y encuestas a empleadores sintéticos, los escribe como CSV de
    ejemplo y los importa con el mismo flujo de validación que usa la app (RF-001, RF-002 y RF-003)."""
    cfg_cen = rubrica["fuentes"]["ceneval"]
    nombres = dict(ALUMNOS)

    calificaciones = []
    for matricula, habilidad in habilidades.items():
        for asig in ASIGNATURAS:
            nota = round(min(max(52 + (habilidad - 1) * 14 + rng.uniform(-6, 6), 40), 100))
            calificaciones.append([matricula, nombres[matricula], asig, PERIODO, nota])
    df_cal = pd.DataFrame(calificaciones, columns=importacion.COLUMNAS["calificaciones"])

    ceneval = []
    for matricula, habilidad in habilidades.items():
        puntaje = round(min(max(860 + (habilidad - 1) * 115 + rng.uniform(-60, 60), 700), 1300))
        desempeno = "ANS" if puntaje < 1000 else "DS" if puntaje < 1150 else "DSS"
        ceneval.append([matricula, nombres[matricula], cfg_cen["examen"], cfg_cen["areas"][0], PERIODO, desempeno, puntaje])
    df_cen = pd.DataFrame(ceneval, columns=importacion.COLUMNAS["ceneval"])

    # Encuestas: la valoración de cada empleador sigue la habilidad promedio de la generación, con ruido.
    promedio = sum(habilidades.values()) / len(habilidades)
    encuestas = []
    for empleador in EMPLEADORES:
        respuesta = round(min(max(1 + (promedio - 1) * 1.1 + rng.uniform(-0.8, 0.8), 1), 5) * 2) / 2
        encuestas.append([empleador, AE_ID, PERIODO, respuesta, "SI"])
    encuestas.append(["Empresa Sin Consentimiento (ejemplo)", AE_ID, PERIODO, 2, "NO"])  # se omite
    df_enc = pd.DataFrame(encuestas, columns=importacion.COLUMNAS["encuestas"])
    df_enc.to_csv(EJEMPLOS_DIR / "encuestas_ejemplo.csv", index=False, encoding="utf-8-sig")

    # Archivo con errores intencionales para demostrar la validación en la página de carga.
    errores = df_cal.copy()
    errores.loc[len(errores)] = ["A0101", "", "Cálculo Diferencial", PERIODO, 90]   # no tributa al AE: se omite
    errores.loc[len(errores)] = ["", "Sin Matrícula", ASIGNATURAS[0], PERIODO, 80]  # falta matrícula
    errores.loc[len(errores)] = ["A0102", "", ASIGNATURAS[0], "2026/1", 85]        # periodo inválido
    errores.loc[len(errores)] = ["A0103", "", ASIGNATURAS[1], PERIODO, 105]        # fuera de rango

    df_cal.to_csv(EJEMPLOS_DIR / "calificaciones_ejemplo.csv", index=False, encoding="utf-8-sig")
    df_cen.to_csv(EJEMPLOS_DIR / "ceneval_ejemplo.csv", index=False, encoding="utf-8-sig")
    errores.to_csv(EJEMPLOS_DIR / "calificaciones_con_errores.csv", index=False, encoding="utf-8-sig")

    rubricas = {rubrica["id"]: rubrica}
    n_cal = importacion.importar(importacion.validar_calificaciones(df_cal, rubricas, "calificaciones_ejemplo.csv"))
    n_cen = importacion.importar(importacion.validar_ceneval(df_cen, rubricas, "ceneval_ejemplo.csv"))
    n_enc = importacion.importar(importacion.validar_encuestas(df_enc, rubricas, "encuestas_ejemplo.csv"))
    return {"calificaciones": n_cal, "resultados_ceneval": n_cen, "encuestas": n_enc}


if __name__ == "__main__":
    print(sembrar())
