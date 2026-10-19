import io
from pathlib import Path


def texto_de_archivo(nombre: str, contenido: bytes) -> str:
    """Extrae texto plano de una evidencia. TXT/MD siempre; PDF y DOCX si están instaladas las librerías."""
    ext = Path(nombre).suffix.lower()

    if ext in (".txt", ".md"):
        return contenido.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("Para leer PDF instala pypdf: pip install pypdf")
        lector = PdfReader(io.BytesIO(contenido))
        return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)

    if ext == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise ValueError("Para leer DOCX instala python-docx: pip install python-docx")
        documento = Document(io.BytesIO(contenido))
        return "\n".join(p.text for p in documento.paragraphs)

    raise ValueError(f"Formato no soportado: {ext or 'sin extensión'}")
