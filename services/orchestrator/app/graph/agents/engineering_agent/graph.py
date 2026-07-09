from ..base.agent_factory import build_domain_agent
from .prompt import ENGINEERING_AGENT_PROMPT
from .tools import check_service_status
from langchain.chat_models import init_chat_model

llm = init_chat_model(model="groq:llama-3.3-70b-versatile", temperature=0.2, streaming=True)

engineering_agent = build_domain_agent(
    llm=llm,
    system_prompt=ENGINEERING_AGENT_PROMPT,
    tools= [check_service_status],
    domain_name="engineering"
)