from ..base.agent_factory import build_domain_agent
from .prompt import FINANCE_AGENT_PROMPT
from .tools import create_claim, flag_invoice_discrepancy, change_claim_status
from langchain.chat_models import init_chat_model

llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

finance_agent = build_domain_agent(
    llm=llm,
    system_prompt=FINANCE_AGENT_PROMPT,
    tools=[create_claim, flag_invoice_discrepancy, change_claim_status],
    domain_name="finance",
    retrieval_method = ["sql","vector"],
    sql_function = ["claim_tracking"]
)