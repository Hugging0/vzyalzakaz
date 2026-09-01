from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader


def extract_document_text(path: Path, mime_type: str | None) -> str:
    """Extract a bounded summary source from common portfolio documents."""
    suffix = path.suffix.lower()
    if mime_type == "application/pdf" or suffix == ".pdf":
        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:20])
    elif (
        mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or suffix == ".docx"
    ):
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    elif suffix in {".txt", ".md", ".rtf"} or (mime_type or "").startswith("text/"):
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:1500]
