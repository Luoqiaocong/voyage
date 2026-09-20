"""auth 模块常量。"""

# 邮箱验证码长度
VERIFY_CODE_LENGTH = 6
# 邮箱验证码 Redis 键前缀
VERIFY_CODE_KEY_PREFIX = "verify_code:"
# 验证码有效期（秒）
VERIFY_CODE_TTL_SECONDS = 180

# 发送验证码时同步等待邮件投递的上限（秒）。
#
# Resend 一次 SMTP 投递约 4 秒（TCP + STARTTLS + 认证 + 投递），
# 且相当稳定地超过 2 秒。因此把等待窗口放大并没有意义——
# 大多数请求都会超时转入后台，用户却白白多等那么久。
#
# 取 0.8 秒的权衡：
#   - 按钮能迅速恢复，主观上「点了有反应」
#   - 极快的失败（配置缺失、DNS 失败）仍能在窗口内拿到确定结果
#   - 正常情况下返回「邮件正在发送」，由前端文案说明稍等片刻
# 配合前端的倒计时与提示，用户不会误以为没发送成功。
CODE_FAST_WAIT_SECONDS = 0.8

VERIFY_TOKEN_PREFIX = "verify_token:"
VERIFY_TOKEN_TTL_SECONDS = 300

# Refresh Token Redis 键前缀
REFRESH_KEY_PREFIX = "refresh:"
REFRESH_USER_KEY_PREFIX = "refresh_user:"