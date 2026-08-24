from pathlib import Path
import os
from langsmith import traceable

os.environ.setdefault("USER_AGENT", "PRODAPI/1.0")

from langchain_community.document_loaders import (
    TextLoader,
    DirectoryLoader, 
    PyMuPDFLoader,
    WebBaseLoader
)
@traceable(name="load_documents_from_directory", category="document_loaders", tags=["document", "loader", "directory"])
def load_documents_from_directory(directory_path):
    """
    Load documents from a specified directory using DirectoryLoader.

    Args:
        directory_path (str): The path to the directory containing documents.
    """
    urls = [
    "https://www.geeksforgeeks.org/nlp/what-is-retrieval-augmented-generation-rag/",
    "https://azure.microsoft.com/en-us/resources/cloud-computing-dictionary/what-are-large-language-models-llms",
    "https://www.simplilearn.com/tutorials/artificial-intelligence-tutorial/what-is-retrieval-augmented-generation"
]
    text_loader = DirectoryLoader(
        directory_path,
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    pdf_loader = DirectoryLoader(
        directory_path, 
        glob="*.pdf", 
        loader_cls=PyMuPDFLoader
    )
    web_loader = WebBaseLoader(urls)

    return text_loader.load() + pdf_loader.load() + web_loader.load()

if __name__ == "__main__":

    directory_path = Path(__file__).parent / "data"
    documents = load_documents_from_directory(str(directory_path))

    print(f"Loaded {len(documents)} documents from {directory_path}.")
    # for doc in documents:
    #     print(f"Document: {doc.metadata['source']}, Content: {doc.page_content[:100]}...")  # Print first 100 characters of content