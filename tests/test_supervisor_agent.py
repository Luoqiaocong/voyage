import pytest
from langchain.messages import HumanMessage

from app.core.agent import get_agent

agent = get_agent()
@pytest.mark.asyncio
async def test_supervisor_agent():
    stream = agent.astream(
        {"messages": [HumanMessage(content="你是什么模型？")]},
        stream_mode="messages",
    )

    chunks = []
    async for event in stream:
        if isinstance(event, tuple) and len(event) >= 1:
            msg = event[0]
            content = getattr(msg, "content", None)
            if content:
                if isinstance(content, str):
                    chunks.append(content)
                    print(content, end="", flush=True)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")
                            chunks.append(text)
                            print(text, end="", flush=True)

    print()  # 换行

    # 真正的断言：有输出才算通过
    assert chunks, "agent 没有返回任何内容"
    full_text = "".join(chunks)
    assert len(full_text) > 0