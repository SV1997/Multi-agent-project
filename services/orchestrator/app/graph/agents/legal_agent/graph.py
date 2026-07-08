from langchain.chat_models import init_chat_model
from ..base.agent_factory import build_domain_agent
from .prompt import LEGAL_SYSTEM_PROMPT
from .tools import check_compliance_status
from dotenv import load_dotenv
load_dotenv()
llm = init_chat_model(model="groq:llama-3.3-70b-versatile", temperature=0.2, streaming=True)

legal_agent = build_domain_agent(
    llm=llm,
    system_prompt=LEGAL_SYSTEM_PROMPT,
    tools=[check_compliance_status],
    domain_name="legal"
)

