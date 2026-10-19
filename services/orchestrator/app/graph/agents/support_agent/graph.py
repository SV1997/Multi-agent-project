from ..base.agent_factory import build_domain_agent
from .prompt import SUPPORT_AGENT_PROMPT
from .tools import create_ticket, escalate_ticket, change_ticket_status
from langchain.chat_models import init_chat_model

llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

support_agent = build_domain_agent(
    llm=llm,
    system_prompt=SUPPORT_AGENT_PROMPT,
    tools=[create_ticket, escalate_ticket, change_ticket_status],
    domain_name="support",
    retrieval_method=["sql", "vector"],
    sql_function=["get_ticket_status"]
)