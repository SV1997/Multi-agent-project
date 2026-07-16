from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Literal
from .state import AgentState
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT
from .agents.legal_agent.graph import legal_agent
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT
from .agents.hr_agent.graph import hr_agent
from .agents.engineering_agent.graph import engineering_agent
from .agents.support_agent.graph import support_agent
from .agents.coding_agent.graph import coding_agent
from langgraph.checkpoint.memory import MemorySaver
from .hitl.interrupts import human_review_gate

checkpointer = MemorySaver()

def set_supervisor_agent():
    class DomainClassification(BaseModel):
        domain: Literal["legal","hr","engineering","coding","support"] = Field(description="It provide routing detail for the tool base on the literal")

    classifier_llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=True).with_structured_output(DomainClassification, method="json_schema", strict=True).with_config(tags=["classification-only"])

    async def classify_domain(state: AgentState)-> dict:
        prompt = SUPERVISOR_ROUTE_PROMPT

        messages = [SystemMessage(content=prompt)] + state["messages"]

        decision = await classifier_llm.ainvoke(messages)
        print(decision.domain)
        
        return{
            "domain": decision.domain,
            
        }

    def check_authorization(state:AgentState)->dict:
        allowed = state.get("allowed_namespace")
        classified_domains = [state["domain"]]
        print(allowed, classified_domains)
        unauthorized = [d for d in classified_domains if d not in allowed]
        if(unauthorized):
            return {"authorization_denied": True, "denied_domain":unauthorized}
        return {"authorization_denied": False}

    def route_to_agent(state:AgentState)-> str:
        if state.get("authorization_denied"):
            return "denied"
        return state["domain"]

    def access_denied(state: AgentState) -> dict:
        denial_text = "This query touches a domain you are not authorized to access."
        return {
        "messages": [AIMessage(content=denial_text)],
        "final_answer": {
            "domain": state.get("domain"),
            "answer": denial_text,
            "sources": [],
            "confidence": 1.0,
            "requires_human_review": False,
        }
    }
        

    graph = StateGraph(AgentState)
    graph.set_entry_point("classify_domain")
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("check_authorization", check_authorization)
    graph.add_node("legal_agent", legal_agent)
    graph.add_node("hr_agent", hr_agent)
    graph.add_node("engineering_agent", engineering_agent)
    graph.add_node("support_agent", support_agent)
    graph.add_node("coding_agent", coding_agent)
    graph.add_node("human_review_gate",human_review_gate)
    graph.add_node("access_denied",access_denied)
    graph.add_edge("classify_domain","check_authorization")
    graph.add_conditional_edges(
        "check_authorization", route_to_agent,{
            "legal":"legal_agent",
            "hr" : "hr_agent",
            "coding": "coding_agent",
            "support": "support_agent",
            "engineering": "engineering_agent",
            "denied": "access_denied"
        }
    )
    graph.add_edge("coding_agent", "human_review_gate")
    graph.add_edge("legal_agent", "human_review_gate")
    graph.add_edge("hr_agent", "human_review_gate")
    graph.add_edge("engineering_agent", "human_review_gate")
    graph.add_edge("support_agent", "human_review_gate")
    graph.add_edge("human_review_gate", END)
    graph.add_edge("access_denied", END)
    return graph.compile(checkpointer=checkpointer)


supervisor = set_supervisor_agent()
 




