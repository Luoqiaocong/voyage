"""Resend 发信冒烟测试脚本：读取 .env 中的 RESEND_API_KEY，向指定邮箱发送测试邮件。

用法:
    uv run python test_resend.py              # 交互输入收件邮箱
    uv run python test_resend.py user@qq.com  # 直接传收件邮箱
"""
import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parent / ".env"
FROM_ADDRESS = "noreply@v.hiseven.cn"
FROM_NAME = "Voyage AI"


def load_key() -> str:
    env = dotenv_values(ENV_PATH)
    key = (env.get("RESEND_API_KEY") or "").strip()
    if not key:
        raise SystemExit("未在 .env 中找到 RESEND_API_KEY")
    return key


async def main() -> None:
    to = sys.argv[1] if len(sys.argv) > 1 else input("收件邮箱: ").strip()
    key = load_key()
    payload = {
        "from": f"{FROM_NAME} <{FROM_ADDRESS}>",
        "to": [to],
        "subject": "Voyage AI 邮件发送测试",
        "html": (
            "<div style='font-family:Microsoft YaHei,Arial,sans-serif;"
            "max-width:520px;margin:0 auto;border:1px solid #e5e7eb;"
            "border-radius:12px;padding:24px'>"
            "<h2 style='color:#1f2937'>测试成功</h2>"
            "<p style='color:#4b5563'>这是一封来自 <b>v.hiseven.cn</b> 域名、"
            "通过 <b>Resend</b> 发送的测试邮件。</p>"
            "<p style='color:#4b5563'>收到这封邮件，说明域名验证与 API 接入全部正常。</p>"
            "<p style='color:#9ca3af;font-size:12px'>Voyage AI · smart travel planning</p>"
            "</div>"
        ),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        print(f"HTTP {resp.status_code}")
        print(resp.text)
        if resp.status_code >= 400:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())