from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


class UnsupportedSourceError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    page_number: int | None


def extract_file(filename: str, data: bytes) -> tuple[str, list[ExtractedPage]]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        text = data.decode("utf-8", errors="replace").strip()
        return ("text/markdown" if suffix == ".md" else "text/plain", [ExtractedPage(text)])
    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(data))
            pages = [
                ExtractedPage(text=(page.extract_text() or "").strip(), page_number=index + 1)
                for index, page in enumerate(reader.pages)
            ]
        except Exception as exc:
            raise UnsupportedSourceError("The PDF could not be read") from exc
        return "application/pdf", [page for page in pages if page.text]
    raise UnsupportedSourceError("Only PDF, TXT, and Markdown files are supported")


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    chunk_characters: int,
    overlap: int,
) -> list[ChunkDraft]:
    if overlap >= chunk_characters:
        raise ValueError("Chunk overlap must be smaller than chunk size")
    chunks: list[ChunkDraft] = []
    step = chunk_characters - overlap
    for page in pages:
        normalized = " ".join(page.text.split())
        for start in range(0, len(normalized), step):
            content = normalized[start : start + chunk_characters].strip()
            if content:
                chunks.append(ChunkDraft(content=content, page_number=page.page_number))
            if start + chunk_characters >= len(normalized):
                break
    return chunks
