import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
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

