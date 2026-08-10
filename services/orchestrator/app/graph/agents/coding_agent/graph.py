from ..base.agent_factory import build_domain_agent
from .prompt import CODING_AGENT_PROMPT
from .tools import check_for_bug
from langchain.chat_models import init_chat_model

llm = init_chat_model(model="groq:openai/gpt-oss-120b", temperature=0.2, streaming=True)

coding_agent = build_domain_agent(
    llm=llm,
    system_prompt=CODING_AGENT_PROMPT,
    tools=[check_for_bug],
    domain_name="coding"
)