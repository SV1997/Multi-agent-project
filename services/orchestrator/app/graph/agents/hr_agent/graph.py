from langchain.chat_models import init_chat_model
from ..base.agent_factory import build_domain_agent
from .tools import check_balance_leaves
from .prompt import HR_AGENT_PROMPT

llm = init_chat_model(model="groq:llama-3.3-70b-versatile", temperature=0.2, streaming=True)


hr_agent = build_domain_agent(
    llm=llm,
    system_prompt=HR_AGENT_PROMPT,
    tools= [check_balance_leaves],
    domain_name="hr"
)