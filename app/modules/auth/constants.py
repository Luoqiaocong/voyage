"""auth 模块常量。"""

# 邮箱验证码长度
VERIFY_CODE_LENGTH = 6
# 邮箱验证码 Redis 键前缀
VERIFY_CODE_KEY_PREFIX = "verify_code:"
# 验证码有效期（秒）
VERIFY_CODE_TTL_SECONDS = 180