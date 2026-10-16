"""Feature 3: parse-quality warnings. Run from services/ingestion_service: python -m pytest tests/test_parse_quality.py"""
import os
import sys

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from app.loader.encoder import assess_parse_quality  # noqa: E402


def _text_pdf(path: str, pages: int = 2) -> None:
    """Minimal hand-built PDF with a real text layer (no PDF library available)."""
    body = " ".join(["Employees receive twenty days of annual leave per calendar year."] * 6)
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + i} 0 R' for i in range(pages))}] /Count {pages} >>"]
    for i in range(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {3 + pages + i} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>")
    for _ in range(pages):
        stream = f"BT /F1 10 Tf 20 700 Td ({body}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out, offsets = "%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    with open(path, "wb") as f:
        f.write(out.encode("latin-1"))


def test_scanned_pdf_warns(tmp_path):
    path = str(tmp_path / "scan.pdf")
    Image.new("RGB", (300, 300), "white").save(path)  # image-only PDF, no text layer
    warnings = assess_parse_quality(PyPDFLoader(path).load(), "pdf")
    assert any("no extractable text on page 1" in w for w in warnings)
    assert any("scanned" in w for w in warnings)


def test_normal_pdf_has_no_warnings(tmp_path):
    path = str(tmp_path / "normal.pdf")
    _text_pdf(path)
    docs = PyPDFLoader(path).load()
    assert len(docs) == 2 and docs[0].page_content.strip()
    assert assess_parse_quality(docs, "pdf") == []


def test_table_heavy_text_warns():
    rows = "\n".join(f"Item {i}  |  {i * 10}  |  USD" for i in range(10))
    assert any("tables" in w for w in assess_parse_quality([Document(page_content=rows)], "markdown"))
