import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
import re
import tempfile
from urllib.parse import urlparse
import requests
from langchain_community.document_loaders import (
    PyPDFLoader,
    WebBaseLoader,
    UnstructuredMarkdownLoader
)
from langchain_core.documents import Document

def load_from_pdf(file_path:str)->list[Document]:
    loader = PyPDFLoader(file_path)
    return loader.load()

def load_from_url(url:str)->list[Document]:
    loader = WebBaseLoader(url)
    return loader.load()

def load_from_markdown(file_path:str)-> list[Document]:
    loader = UnstructuredMarkdownLoader(file_path)
    return loader.load()

LOADERS = {
    "pdf": load_from_pdf,
    "url": load_from_url,
    "markdown": load_from_markdown
}

def _is_remote(source:str)->bool:
    return urlparse(source).scheme in ("http", "https")

# SeaweedFS's presigned URL comes back as http://localhost:8333/bucket/key?X-Amz-Algorithm=... — scheme http, so it's correctly seen as remote.
# The bug wasn't that PyPDFLoader can't handle URLs at all — it can, it just tries to be clever about the temp filename it downloads to. It first checks "is this an AWS presigned URL?" (only matches *.s3.amazonaws.com hosts) — that check failed for localhost:8333.
# Falling back to its generic path, it took os.path.splitext() of the whole URL string including the query string. Since there's no . after .pdf inside the query string, splitext treated everything from .pdf to the end (.pdf?X-Amz-Algorithm=...&x-id=GetObject) as the file "extension."
# That produced a temp filename containing ?, which is an illegal character on Windows — so the file write/read failed with "No such file or directory."
# So yes: it got confused deriving the suffix/filetype from the URL, not because it fundamentally can't fetch a URL. My fix sidesteps that entirely by downloading the bytes ourselves and giving the temp file a clean, hardcoded .pdf/.md suffix before the loader ever sees it.


EMPTY_PAGE_CHARS = 20          # a page with fewer non-space characters than this counts as empty
MIN_AVG_CHARS_PER_PAGE = 200
MAX_EMPTY_PAGE_RATIO = 0.3
MAX_TABLE_LINE_SHARE = 0.3
MAX_PAGE_WARNINGS = 5

def _is_table_like(line: str) -> bool:
    return line.count("|") >= 2 or line.count("\t") >= 2 or len(re.findall(r"\S {2,}\S", line)) >= 2

def assess_parse_quality(docs: list[Document], source_type: str) -> list[str]:
    """Flag (never fix) signs of a poor parse: empty pages, thin text, table-heavy content."""
    warnings: list[str] = []
    if not docs:
        return ["document produced no content"]
    texts = [d.page_content for d in docs]
    if source_type == "pdf":
        empty = [i for i, t in enumerate(texts) if len(t.strip()) < EMPTY_PAGE_CHARS]
        for i in empty[:MAX_PAGE_WARNINGS]:
            page = docs[i].metadata.get("page", i)
            warnings.append(f"no extractable text on page {int(page) + 1}")
        if len(empty) > MAX_PAGE_WARNINGS:
            warnings.append(f"no extractable text on {len(empty) - MAX_PAGE_WARNINGS} more pages")
        if len(empty) / len(texts) > MAX_EMPTY_PAGE_RATIO:
            warnings.append(f"{len(empty)}/{len(texts)} pages are empty - the file may be scanned; OCR is not applied")
        avg = sum(len(t) for t in texts) / len(texts)
        if avg < MIN_AVG_CHARS_PER_PAGE:
            warnings.append(f"low text density: {avg:.0f} characters per page")
    lines = [ln for t in texts for ln in t.splitlines() if ln.strip()]
    if lines:
        share = sum(_is_table_like(ln) for ln in lines) / len(lines)
        if share > MAX_TABLE_LINE_SHARE:
            warnings.append(f"{share:.0%} of lines look like tables; table structure may be lost in chunks")
    return warnings

def load_document(source:str, source_type:str)->list[Document]:
    if source_type not in LOADERS:
        raise ValueError(
            f"Unsupported source type: {source_type}. "
            f"Must be one of: {list(LOADERS.keys())}"
        )

    if source_type == "url":
        return load_from_url(source)

    if not _is_remote(source):
        return LOADERS[source_type](source)

    suffix = ".pdf" if source_type == "pdf" else ".md"
    response = requests.get(source)
    response.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(response.content)
        tmp.close()
        return LOADERS[source_type](tmp.name)
    finally:
        os.unlink(tmp.name)

