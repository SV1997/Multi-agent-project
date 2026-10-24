import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))        # services/orchestrator -> `app`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))  # repo root -> `shared`

from app.graph.conversation_memory import extract_relevant_info
TURNS = [
    "Hi, what is the notice period for applying for leave?",
    "I want to apply for earned leave. How many days can I take at once?",
    "The leave would be from 12 Dec to 19 Dec. Does that clash with the year-end freeze?",
    "I also filed a travel claim for 45,000. When is it usually paid?",
    "My laptop ticket INC-48213 is still open. Who handles hardware issues?",
    "Change of plan, my leave will end on 22 Dec instead.",
    "Correction, the travel claim is 42,500, not 45,000.",
    "My colleague's ticket INC-50117 is about the same laptop issue. Is it linked to mine?",
]

async def main():
    notes = []                                   # (id, text), in creation order
    for n, msg in enumerate(TURNS, 1):
        existing = [{"id": i, "text": t} for i, t in notes]
        out = await extract_relevant_info(existing, "", msg)
        print(f"\nturn {n}: {msg}")
        if not out:
            print("   (nothing)")
        for m in out:
            linked = [t for i, t in notes if i in m["linked_ids"]]
            print("   +", m["text"], "| links to:", linked, "| bad:", m["bad_links"])
            notes.append((f"n{len(notes)}", m["text"]))

asyncio.run(main())