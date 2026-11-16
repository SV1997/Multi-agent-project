"""Builds the model that labels chunks (shared/taxonomy/chunk_labeler.py decides how it is used)."""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../.."))
from shared.taxonomy.chunk_labeler import build_openai_labeler
from ..core.config import CHUNK_LABELING_ENABLED, LABELING_MODEL, OPENAI_API_KEY


def build_chunk_labeler():
    """The labelling model, or None when CHUNK_LABELING is off (chunks then get their document's whole list, as before)."""
    if not CHUNK_LABELING_ENABLED:
        return None
    return build_openai_labeler(LABELING_MODEL, OPENAI_API_KEY)
