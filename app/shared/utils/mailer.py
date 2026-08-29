"""通用邮件发送模块（Resend SMTP · aiosmtplib）。

纯工具层约定：
- 不依赖任何业务异常 / 错误码，不在此层记录日志；
- 发送结果统一以 bool 返回：成功 True，失败 False；
- 异常转化、日志、业务错误码等一律交由上层 service 处理。

传输方式：SMTP 直连（默认 smtp.resend.com，端口 587 + STARTTLS，
用户名固定 resend，密码即 RESEND_API_KEY）。SMTP 连接参数可通过
config 的 SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD 切换供应商。
"""
from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.config import config

SMTP_TIMEOUT_SECONDS = 15.0


def _build_verification_html(*, code: str, expire_minutes: int) -> str:
    """构建验证码邮件 HTML（渐变精致风，全内联样式，兼容 QQ / 163 / Gmail 等主流客户端）。"""
    brand = config.MAIL_FROM_NAME
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background-color:#eef4f9;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef4f9;padding:40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;width:100%;background-color:#ffffff;border-radius:16px;box-shadow:0 12px 32px rgba(15,23,42,0.08);padding:40px 32px 32px;">
          <tr>
            <td style="font-family:'Microsoft YaHei','PingFang SC',sans-serif;color:#0f172a;text-align:center;">
              <div style="width:64px;height:5px;background:linear-gradient(90deg,#3b82f6,#60a5fa);border-radius:3px;margin:0 auto 28px;"></div>
              <div style="font-size:22px;font-weight:700;letter-spacing:1px;line-height:1.4;">邮箱验证</div>
              <div style="font-size:14px;color:#64748b;margin-top:10px;line-height:1.6;">您好！请使用以下验证码完成验证</div>
              <div style="margin:32px 0 0;text-align:center;">
                <span style="display:inline-block;padding:18px 42px;background-color:#3b82f6;background-image:linear-gradient(135deg,#3b82f6,#60a5fa);border-radius:12px;box-shadow:0 6px 18px rgba(59,130,246,0.28);font-family:Consolas,'Courier New',monospace;font-size:32px;font-weight:700;letter-spacing:10px;color:#ffffff;">{code}</span>
              </div>
              <div style="font-size:13px;color:#64748b;margin-top:28px;">验证码 <b style="color:#2563eb;">{expire_minutes} 分钟内有效</b>，请勿向他人泄露</div>
              <div style="font-size:12px;color:#94a3b8;margin-top:8px;">如非本人操作，请忽略本邮件</div>
            </td>
          </tr>
        </table>
        <div style="font-family:Arial,sans-serif;font-size:12px;color:#94a3b8;margin-top:20px;text-align:center;line-height:1.8;">
          本邮件由 {brand} AI 自动发送，请勿直接回复 · v.hiseven.cn
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""


async def _send_smtp(*, to: str, subject: str, html: str, text: str | None) -> bool:
    """通过 SMTP（aiosmtplib）发送邮件，返回是否成功。"""
    if not config.RESEND_API_KEY:
        return False

    message = EmailMessage()
    message["From"] = f"{config.MAIL_FROM_NAME} <{config.MAIL_FROM_ADDRESS}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text or "请使用支持 HTML 的邮件客户端查看本邮件。")
    message.add_alternative(html, subtype="html")
    
    """
    根据 MIME 协议的 multipart/alternative 标准，邮件客户端会按照 "后添加的优先" 原则来处理内容：
      1.如果客户端支持 HTML → 显示最后添加的 HTML 版本
      2.如果客户端不支持 HTML → 显示纯文本版本
    """
    

    password = config.RESEND_API_KEY
    try:
        await aiosmtplib.send(
            message,
            hostname=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USER,
            password=password,
            start_tls=True,
            timeout=SMTP_TIMEOUT_SECONDS,
        )
        return True
    except Exception:
        # 工具层不消化细节，统一按失败返回，由上层 service 记录与转义
        return False


async def send_verification_code(
    to: str,
    code: str,
    expire_minutes: int = 3,
) -> bool:
    """发送验证码邮件。

    Args:
        to: 收件人邮箱
        code: 验证码（建议 6 位数字字符串）
        expire_minutes: 验证码有效期（分钟）

    Returns:
        bool: 发送成功返回 True，否则返回 False
    """
    subject = f"【{config.MAIL_FROM_NAME}】邮箱验证码"
    html = _build_verification_html(
        code=code,
        expire_minutes=expire_minutes,
    )
    text = (
        f"您好！您的验证码为：{code}\n"
        f"该验证码 {expire_minutes} 分钟内有效，请勿向他人泄露。\n\n"
        f"—— {config.MAIL_FROM_NAME} AI · v.hiseven.cn"
    )
    return await _send_smtp(to=to, subject=subject, html=html, text=text)