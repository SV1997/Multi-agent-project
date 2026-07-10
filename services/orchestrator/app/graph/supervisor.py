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

    classifier_llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0, streaming=True).with_structured_output(DomainClassification, method="json_schema", strict=True)

    async def classify_domain(state: AgentState)-> dict:
        prompt = SUPERVISOR_ROUTE_PROMPT

        messages = [SystemMessage(content=prompt)] + state["messages"]

        decision = await classifier_llm.ainvoke(messages)
        print(decision.domain)
        
        return{
            "domain": decision.domain,
            
        }

    def route_to_agent(state:AgentState)-> str:
        return state["domain"]

    graph = StateGraph(AgentState)
    graph.set_entry_point("classify_domain")
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("legal_agent", legal_agent)
    graph.add_node("hr_agent", hr_agent)
    graph.add_node("engineering_agent", engineering_agent)
    graph.add_node("support_agent", support_agent)
    graph.add_node("coding_agent", coding_agent)
    graph.add_node("human_review_gate",human_review_gate)
    graph.add_conditional_edges(
        "classify_domain", route_to_agent,{
            "legal":"legal_agent",
            "hr" : "hr_agent",
            "coding": "coding_agent",
            "support": "support_agent",
            "engineering": "engineering_agent",
        }
    )
    graph.add_edge("coding_agent", "human_review_gate")
    graph.add_edge("legal_agent", "human_review_gate")
    graph.add_edge("hr_agent", "human_review_gate")
    graph.add_edge("engineering_agent", "human_review_gate")
    graph.add_edge("support_agent", "human_review_gate")
    graph.add_edge("human_review_gate", END)
    return graph.compile(checkpointer=checkpointer)


supervisor = set_supervisor_agent()
 




