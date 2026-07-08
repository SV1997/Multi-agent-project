from langgraph.graph import StateGraph, START, END
from ...state import AgentState
from langgraph.prebuilt import ToolNode
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from .nodes import retrieve_context, build_context_prompt
from langchain_core.prompts import ChatPromptTemplate
def route_after_reason(state:AgentState)-> str:
    msg = state["messages"][-1]
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        if state["tool_calls_remaining"]>0:
            return "tools"
        
    return "end"



def build_domain_agent(llm,system_prompt:str, tools: list = None, domain_name: str = ""):
    tool = tools or []
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_context)

    llm_with_tools = llm.bind_tools(tools) if tool else llm

    async def reason(state:AgentState)-> dict:

        context = build_context_prompt(state)
        print(context)
        msg = state["messages"][-1]
        query = msg.content

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Context:{context}\n\nQuestion:{query}")
            ]
        

        res = await llm_with_tools.ainvoke(messages)
        return {"messages":[res], "tool_calls_remaining": state["tool_calls_remaining"]-1}
    
    graph.add_node("reason", reason)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "reason")
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges("reason",route_after_reason,{"tools":"tools", "end":END})
        graph.add_edge("tools","reason")

    else:
        graph.add_edge("reason",END)
    

    return graph.compile()


