from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from ..core.config import CHUNK_OVERLAP, CHUNK_SIZE

def split_documents(document:list[Document])-> list[Document]:

    spliter = RecursiveCharacterTextSplitter(
        chunk_size = CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    return spliter.split_documents(document)