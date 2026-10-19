import json
import os
import re

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
MAX_CHARS = 12000

ESQUEMA_SALIDA = {
    "type": "object",
    "properties": {
        "evaluaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indicador_id": {"type": "string"},
                    "nivel": {"type": "integer"},
                    "justificacion": {"type": "string"},
                    "citas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["indicador_id", "nivel", "justificacion", "citas"],
            },
        }
    },
    "required": ["evaluaciones"],
}


def estado_motor() -> tuple[str, str]:
    """Devuelve (motor, detalle). El motor es 'ollama' si el servicio local y el modelo están disponibles."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        r.raise_for_status()
        modelos = [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return "heuristico", "Ollama no responde; se usa el evaluador heurístico."
    if not any(m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL + ":") for m in modelos):
        return "heuristico", f"Ollama activo pero falta el modelo (ollama pull {OLLAMA_MODEL}); se usa el heurístico."
    return "ollama", f"Ollama local con {OLLAMA_MODEL}."


def evaluar(texto: str, rubrica: dict) -> tuple[list[dict], str | None]:
    """Evalúa la evidencia contra cada indicador. Devuelve (resultados, aviso)."""
    motor, _ = estado_motor()
    if motor == "ollama":
        try:
            return _evaluar_ollama(texto, rubrica), None
        except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as e:
            return _evaluar_heuristico(texto, rubrica), f"Falló Ollama ({e}); se usó el evaluador heurístico."
    return _evaluar_heuristico(texto, rubrica), None


def _prompt(texto: str, rubrica: dict) -> list[dict]:
    indicadores = "\n\n".join(
        f"Indicador {i['id']} - {i['nombre']}: {i['descripcion']}\n"
        + "\n".join(f"  Nivel {n}: {d}" for n, d in i["niveles"].items())
        for i in rubrica["indicadores"]
    )
    sistema = (
        "Eres un evaluador académico que aplica rúbricas de atributos de egreso. "
        "Evalúa únicamente con base en lo que dice la evidencia. Para cada indicador asigna un nivel "
        "entero del 1 al 4, una justificación breve en español y de 1 a 3 citas textuales copiadas "
        "exactamente de la evidencia. Si no hay sustento, asigna nivel 1 y deja citas vacías."
    )
    usuario = (
        f"Atributo de egreso {rubrica['id']}: {rubrica['nombre']}\n\n{indicadores}\n\n"
        f"--- EVIDENCIA ---\n{texto[:MAX_CHARS]}\n--- FIN ---\n\n"
        "Responde con un objeto por cada indicador."
    )
    return [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]


def _evaluar_ollama(texto: str, rubrica: dict) -> list[dict]:
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": ESQUEMA_SALIDA,
            "options": {"temperature": 0},
            "messages": _prompt(texto, rubrica),
        },
        timeout=300,
    )
    r.raise_for_status()
    datos = json.loads(r.json()["message"]["content"])
    por_id = {e["indicador_id"]: e for e in datos["evaluaciones"]}

    normalizado = _normalizar(texto)
    resultados = []
    for ind in rubrica["indicadores"]:
        if ind["id"] not in por_id:
            raise ValueError(f"el modelo no evaluó {ind['id']}")
        e = por_id[ind["id"]]
        # Solo se conservan citas que realmente aparecen en la evidencia.
        citas = [c.strip() for c in e["citas"] if c.strip() and _normalizar(c) in normalizado][:3]
        resultados.append(
            {
                "indicador_id": ind["id"],
                "nivel": min(max(int(e["nivel"]), 1), 4),
                "justificacion": e["justificacion"].strip(),
                "citas": citas,
                "motor": f"ollama:{OLLAMA_MODEL}",
            }
        )
    return resultados


def _evaluar_heuristico(texto: str, rubrica: dict) -> list[dict]:
    """Línea base sin modelo: nivel según cuántas palabras clave del indicador aparecen."""
    oraciones = [o.strip() for o in re.split(r"(?<=[.!?])\s+|\n+", texto) if o.strip()]
    bajo = texto.lower()
    resultados = []
    for ind in rubrica["indicadores"]:
        encontradas = [p for p in ind["palabras_clave"] if p in bajo]
        n = len(encontradas)
        nivel = 1 if n == 0 else 2 if n <= 2 else 3 if n <= 4 else 4
        citas = [o for o in oraciones if any(p in o.lower() for p in encontradas)][:2]
        resultados.append(
            {
                "indicador_id": ind["id"],
                "nivel": nivel,
                "justificacion": (
                    f"Se encontraron {n} de {len(ind['palabras_clave'])} términos clave"
                    + (f" ({', '.join(encontradas)})." if encontradas else ".")
                ),
                "citas": citas,
                "motor": "heuristico",
            }
        )
    return resultados


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()
