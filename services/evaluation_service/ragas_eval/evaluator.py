import json
import sys
import types
from pathlib import Path

from app.core.config import OPENAI_API_KEY
from datasets import Dataset

# ragas unconditionally calls nest_asyncio.apply() on import. That patch is
# only meant for notebooks with an already-running event loop, and on this
# Python version it breaks asyncio.timeout() ("Timeout should be used inside
# a task"), which ragas wraps every scoring call in - causing every job to
# fail and every score to come back NaN. We're a plain script, not a
# notebook, so make ragas's call to it a no-op.
import nest_asyncio

nest_asyncio.apply = lambda *args, **kwargs: None

# ragas unconditionally imports langchain_community.chat_models.vertexai, a
# submodule langchain-community>=0.4 removed (Vertex AI moved to
# langchain-google-vertexai). Stub it out so `import ragas` succeeds; only
# instantiating ChatVertexAI would fail, and we don't use it.
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _vertexai_stub = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "ChatVertexAI is unavailable: langchain-community>=0.4 removed "
                "Vertex AI support. Install langchain-google-vertexai instead."
            )

    _vertexai_stub.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _vertexai_stub

from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

SERVICE_ROOT = Path(__file__).resolve().parent.parent

import pandas as pd

def evaluate_single(question: str, answer: str, contexts: list[str], confidence: float) -> dict:
    dataset = Dataset.from_list([{
        "question": question,
        "answer": answer,
        "contexts": contexts
    }])

    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    result_df = result.to_pandas()
    
    faithfulness_score = float(result_df["faithfulness"].iloc[0])
    relevancy_score = float(result_df["answer_relevancy"].iloc[0])
    flagged = (faithfulness_score < 0.5) and (confidence >= 0.9)
    
    return {
        "faithfulness": faithfulness_score,
        "answer_relevancy": relevancy_score,
        "flagged": flagged
    }