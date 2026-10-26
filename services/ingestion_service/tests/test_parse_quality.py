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


# ---- blank / garbled / too-few-chunks safeguards ----
from app.loader.encoder import assess_chunking, is_blank  # noqa: E402


def test_near_blank_documents_count_as_blank():
    for text in ("", "   \n\t ", "# Title", "TODO", "Page 1"):
        assert is_blank([Document(page_content=text)]), text
    assert not is_blank([Document(page_content="Employees get 15 days of leave.")])


def test_garbled_text_warns_but_clean_text_does_not():
    garbled = Document(page_content="(cid:12)(cid:45)(cid:7) " * 40, metadata={"page": 0})
    mojibake = Document(page_content="Caf\u00c3\u00a9 \u00c3\u00a8 " * 60, metadata={"page": 0})
    clean = Document(page_content="The leave policy grants twenty days of annual leave per calendar year. " * 6, metadata={"page": 0})
    assert any("garbled" in w for w in assess_parse_quality([garbled], "pdf"))
    assert any("garbled" in w for w in assess_parse_quality([mojibake], "pdf"))
    assert not any("garbled" in w for w in assess_parse_quality([clean], "pdf"))


def test_short_markdown_warns_about_little_text():
    assert any("very little text" in w for w in assess_parse_quality([Document(page_content="# Leave policy\nSee HR.")], "markdown"))


def test_too_few_chunks_warns():
    pages = [Document(page_content="x " * 400, metadata={"page": i}) for i in range(10)]
    assert any("only 2 chunks from 10 pages" in w for w in assess_chunking(pages, pages[:2], "pdf"))
    assert any("only 1 chunk" in w for w in assess_chunking(pages[:1], pages[:1], "markdown"))
    assert assess_chunking(pages, pages * 3, "pdf") == []
