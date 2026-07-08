from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Literal
from .state import AgentState
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT
from .agents.legal_agent.graph import legal_agent
from .prompts.supervisor_routing import SUPERVISOR_ROUTE_PROMPT

def set_supervisor_agent():
    class DomainClassification(BaseModel):
        domain: Literal["legal","hr","engineering","coding","support"] = Field(description="It provide routing detail for the tool base on the literal")

    classifier_llm = init_chat_model(model="groq:llama-3.3-70b-versatile", temperature=0.2, streaming=True).with_structured_output(DomainClassification)

    async def classify_domain(state: AgentState)-> dict:
        prompt = SUPERVISOR_ROUTE_PROMPT

        messages = [SystemMessage(content=prompt)] + state["messages"]

        decision = await classifier_llm.ainvoke(messages)
        
        return{
            "domain": decision.domain,
            
        }

    def route_to_agent(state:AgentState)-> str:
        return state["domain"]

    graph = StateGraph(AgentState)
    graph.set_entry_point("classify_domain")
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("legal_agent", legal_agent)

    graph.add_conditional_edges(
        "classify_domain", route_to_agent,{
            "legal":"legal_agent",
            "hr" : "legal_agent",
            "coding": "legal_agent",
            "support": "legal_agent",
            "engineering": "legal_agent",
        }
    )

    graph.add_edge("legal_agent", END)
    return graph.compile()


supervisor = set_supervisor_agent()
 




