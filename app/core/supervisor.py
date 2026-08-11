from langchain.agents import create_agent
from app.core.llm import get_default_llm

SUPERVISOR_PROMPT = """
You are a helpful assistant. Please answer the following question as best as you can.
"""

supervisor_agent = create_agent(
    model=get_default_llm(),
    tools=[],
    system_prompt=SUPERVISOR_PROMPT,
)