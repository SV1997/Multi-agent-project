import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))

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

def load_document(source:str, source_type:str)->list[Document]:

    loaders={
        "pdf": load_from_pdf,
        "url": load_from_url,
        "markdown": load_from_markdown
    }

    if source_type not in loaders:
        raise ValueError(
            f"Unsupported source type: {source_type}",
            f"Must be one of:  {list(loaders.keys())}"
        )
    return loaders[source_type](source)