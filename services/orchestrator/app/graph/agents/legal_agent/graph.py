from langchain.chat_models import init_chat_model
from ..base.agent_factory import build_domain_agent
from .prompt import LEGAL_SYSTEM_PROMPT
from .tools import create_contract, flag_contract_for_review, change_contract_status
from dotenv import load_dotenv
load_dotenv()
llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

legal_agent = build_domain_agent(
    llm=llm,
    system_prompt=LEGAL_SYSTEM_PROMPT,
    tools=[create_contract, flag_contract_for_review, change_contract_status],
    domain_name="legal",
    retrieval_method=["sql", "vector"],
    sql_function=["contract_tracking"]
)

