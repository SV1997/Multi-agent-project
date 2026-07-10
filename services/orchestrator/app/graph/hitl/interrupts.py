from langgraph.types import interrupt
from ..state import AgentState

def human_review_gate(state:AgentState)->dict:
    if(state.get("requires_human_reviews")):
        feedback = interrupt({
            "message":"This answer need human review to finalise",
            "domain":state.get("domain"),
            "answer": state.get("final_answer")
        })

        final_answer = state.get("final_answer") or {}
        if feedback.get("edited") and feedback.get("revised_answer"):
            final_answer = {**final_answer, "answer": feedback["revised_answer"]}

        return {"final_answer": final_answer, "requires_human_reviews": False}
    return {}
