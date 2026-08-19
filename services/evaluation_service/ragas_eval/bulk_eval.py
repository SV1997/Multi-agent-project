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

def evaulate():
    with open(SERVICE_ROOT / "ragas_results.json") as f:
        raw_results = json.load(f)

        valid_results = [
        r for r in raw_results
        if r.get("answer") and r.get("contexts")
        and "not authorized" not in r["answer"].lower()
        and "cannot help" not in r["answer"].lower()
    ]

        print(f"Using {len(valid_results)} of {len(raw_results)} entries (filtered out empty/errored ones)")

        dataset = Dataset.from_list([
            {
                "question": r["question"],
                "answer":r["answer"],
                "contexts":r["contexts"]
            }
            for r in valid_results
        ])

    result = evaluate(
        dataset,
        metrics = [faithfulness, answer_relevancy]
    )

    print(result)

    result_df = result.to_pandas()
    result_df.to_csv(SERVICE_ROOT / "ragas_scores.csv", index=False)
    print("Saved detailed scores to ragas_scores.csv")

import pandas as pd

def check_confidence_calibration(raw_resuts_path, ragas_scores_path):
    with open(raw_resuts_path) as f:
        raw = json.load(f)

    scores_df = pd.read_csv(ragas_scores_path)

    confidence_lookup = {r["question"]:r["confidence"] for r in raw}

    scores_df["confidence"] = scores_df["user_input"].map(confidence_lookup)

    scores_df["miscalibrated"] = (
        (scores_df["confidence"]>=0.9) & (scores_df["faithfulness"]<0.5)
    )

    print("\n--- Confidence Calibration Check ---")
    print(scores_df[["user_input", "confidence", "faithfulness", "miscalibrated"]].to_string(index=False))

    flagged = scores_df[scores_df["miscalibrated"]]
    print(f"\n{len(flagged)} question(s) show dangerous miscalibration (high confidence, low faithfulness):")

    for _,row in flagged.iterrows():
            print(f"  - \"{row['user_input']}\" (confidence={row['confidence']}, faithfulness={row['faithfulness']:.2f})")

    scores_df.to_csv(SERVICE_ROOT/"callibration_check.csv", index=False)
    return scores_df


if __name__ == "__main__":
    evaulate()
    check_confidence_calibration(SERVICE_ROOT / "ragas_results.json", SERVICE_ROOT / "ragas_scores.csv")
