from langchain.chat_models import init_chat_model
from ..base.agent_factory import build_domain_agent
from .tools import submit_leave_request
from .prompt import HR_AGENT_PROMPT

llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

hr_agent = build_domain_agent(
    llm=llm,
    system_prompt=HR_AGENT_PROMPT,
    tools=[submit_leave_request],
    domain_name="hr",
    retrieval_method=["sql", "vector"],
    sql_function=["leave_balance", "CTC_data"]
)