"""Conector de Google Classroom por archivo: lee el CSV de «Descargar todas las calificaciones»
(o la hoja de cálculo exportada como .xlsx). No necesita credenciales de Google.

Formato del archivo de Classroom:

    Apellidos,Nombre,Dirección de correo electrónico,Tarea 1,Tarea 2
    Fecha,,,1 sept 2026,8 sept 2026
    Puntos,,,100,50
    Torres,Ana,a0101@uabc.edu.mx,85,40

Las tres primeras columnas identifican al alumno y cada columna siguiente es una actividad. Las filas
«Fecha» y «Puntos» (o «Date» y «Points») describen las actividades; una celda vacía es una entrega sin calificar.
"""
import csv
import io
import re
import unicodedata
from pathlib import Path

import pandas as pd

from core.conectores import Lectura

ORIGEN = "classroom"
FILAS_FECHA = {"date", "fecha"}
FILAS_PUNTOS = {"points", "puntos"}
OTRAS_FILAS = {"class average", "promedio de la clase", "average", "promedio"}
PUNTOS_POR_DEFECTO = 100.0


def _clave(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _filas(nombre: str, contenido: bytes) -> list[list[str]]:
    ext = Path(nombre).suffix.lower()
    if ext == ".csv":
        for codificacion in ("utf-8-sig", "latin-1"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        return [[c.strip() for c in fila] for fila in csv.reader(io.StringIO(texto))]
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(contenido), header=None, dtype=str, keep_default_na=False)
        return [[str(c).strip() for c in fila] for fila in df.values.tolist()]
    raise ValueError(f"Formato no soportado: {ext or 'sin extensión'}. Usa el CSV de Classroom o un Excel (.xlsx).")


def leer(nombre: str, contenido: bytes) -> Lectura:
    filas = [f for f in _filas(nombre, contenido) if any(f)]
    if not filas or len(filas[0]) < 4:
        raise ValueError(
            "El archivo no parece una exportación de calificaciones de Classroom: se esperan las columnas de "
            "apellidos, nombre y correo, y después una columna por actividad."
        )
    encabezado = filas[0]
    columnas = {i: n for i, n in enumerate(encabezado) if i >= 3 and n}  # índice -> actividad
    if not columnas:
        raise ValueError("El archivo no tiene columnas de actividades.")

    puntos, fechas, alumnos = {}, {}, []
    for n, fila in enumerate(filas[1:], start=2):
        fila = fila + [""] * (len(encabezado) - len(fila))
        etiqueta = _clave(fila[0])
        sin_alumno = not fila[1] and not fila[2]
        if sin_alumno and etiqueta in FILAS_FECHA:
            fechas = {i: fila[i] for i in columnas}
        elif sin_alumno and etiqueta in FILAS_PUNTOS:
            puntos = {i: fila[i] for i in columnas}
        elif sin_alumno and etiqueta in OTRAS_FILAS:
            continue
        else:
            alumnos.append((n, fila))

    def _puntos(i) -> float:
        try:
            p = float(str(puntos.get(i, "")).replace(",", "."))
            return p if p > 0 else PUNTOS_POR_DEFECTO
        except ValueError:
            return PUNTOS_POR_DEFECTO

    lectura = Lectura(origen=ORIGEN)
    lectura.actividades = [{"nombre": n, "puntos": _puntos(i), "fecha": fechas.get(i, "")} for i, n in columnas.items()]
    for n, fila in alumnos:
        nombre_alumno = " ".join(p for p in (fila[1], fila[0]) if p)  # "Nombre Apellidos"
        for i, actividad in columnas.items():
            lectura.entregas.append({
                "fila": n, "nombre": nombre_alumno, "correo": fila[2].lower(), "matricula": "",
                "actividad": actividad, "valor": fila[i], "puntos": _puntos(i),
            })
    return lectura
