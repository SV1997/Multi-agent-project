from ..base.agent_factory import build_domain_agent
from .prompt import SUPPORT_AGENT_PROMPT
from .tools import check_system_compliance
from langchain.chat_models import init_chat_model

llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

support_agent = build_domain_agent(
    llm=llm,
    system_prompt=SUPPORT_AGENT_PROMPT,
    tools=[check_system_compliance],
    domain_name="support"
)