"""Datos de ejemplo: alumnos, asignaturas y evidencias sintéticas para la rúbrica AE-03.

Uso: python -m core.seed
"""
import random
from pathlib import Path

from core import db
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

    for matricula, nombre in ALUMNOS:
        alumno_id = db.obtener_o_crear_alumno(matricula, nombre)
        habilidad = rng.uniform(1.4, 3.9)
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

    return {"alumnos": len(ALUMNOS), "asignaturas": len(ASIGNATURAS), "evidencias": evidencias}


if __name__ == "__main__":
    print(sembrar())
