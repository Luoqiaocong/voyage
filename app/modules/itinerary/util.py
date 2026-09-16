"""行程模块的工具函数。"""
import secrets


def generate_share_token() -> str:
    """生成分享令牌。

    用 secrets.token_urlsafe(32)：约 256 bit 熵，来自操作系统 CSPRNG，
    不可预测也不可枚举。相比 uuid4（122 bit）有更大安全余量，且 URL 安全
    （只含 [A-Za-z0-9_-]），无需再做百分号编码。

    长度约 43 字符，与模型里 String(64) 的容量留有充足余量。
    """
    return secrets.token_urlsafe(32)
