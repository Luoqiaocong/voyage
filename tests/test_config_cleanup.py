"""验证配置清理结果。

要点：
  1. 被删的 5 个字段（DashScope ×2、ALIYUN ×2、DeepSeek 之外的历史项）确实消失
  2. 保留的 DeepSeek 4 项仍在，且**未配置也不阻塞启动**
  3. .env 里遗留的旧键不会导致启动失败（pydantic 默认忽略未声明字段）
  4. 应用仍能正常 import（等价于启动的第一步）
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

REMOVED = [
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_BASE_URL",
    "ALIYUN_BASE_URL",
    "ALIYUN_LLM_MODEL",
]
KEPT = [
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_LLM_MODEL_FLASH",
    "DEEPSEEK_LLM_MODEL_PRO",
]

ok = bad = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global ok, bad
    ok += cond
    bad += not cond
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


cfg_src = Path("app/config.py").read_text(encoding="utf-8")
ex_src = Path(".env.example").read_text(encoding="utf-8")

print("=== 1. 已移除的字段不应再出现在声明中 ===")
for k in REMOVED:
    in_cfg = re.search(rf"^\s{{4}}{k}\s*:", cfg_src, re.M)
    check(f"config.py 已移除 {k}", in_cfg is None)

print("\n=== 2. DeepSeek 配置应完整保留 ===")
for k in KEPT:
    in_cfg = re.search(rf"^\s{{4}}{k}\s*:", cfg_src, re.M)
    in_ex = re.search(rf"^\s*{k}\s*=", ex_src, re.M)
    check(f"config.py 保留 {k}", in_cfg is not None)
    check(f".env.example 保留 {k}", in_ex is not None)

print("\n=== 3. 未配置 DeepSeek 也能加载（不应是必填）===")
# 用**字段架构**判断是否必填，而不是读运行时值：
# 本机 .env 里填了 DEEPSEEK_API_KEY，读运行时值只会拿到真实密钥，
# 证明不了「不填也能启动」。判定依据应当是「该字段有没有默认值」。
from app.config import VoyageConfig

fields = VoyageConfig.model_fields
check("DEEPSEEK_API_KEY 声明了默认值（非必填）",
      fields["DEEPSEEK_API_KEY"].is_required() is False,
      f"is_required={fields['DEEPSEEK_API_KEY'].is_required()}")
check("DEEPSEEK_BASE_URL 声明了默认值",
      fields["DEEPSEEK_BASE_URL"].is_required() is False)
check("DeepSeek 模型名有默认值",
      fields["DEEPSEEK_LLM_MODEL_FLASH"].default == "deepseek-v4-flash",
      repr(fields["DEEPSEEK_LLM_MODEL_FLASH"].default))
# 真正使用的通道仍应是必填 —— 缺失就该启动失败，避免线上静默不可用
check("OPENCODE_API_KEY 仍是必填（缺失应启动失败）",
      fields["OPENCODE_API_KEY"].is_required() is True)
check("OPENCODE_GO_URL 仍是必填",
      fields["OPENCODE_GO_URL"].is_required() is True)
check("已删字段不再存在",
      "DASHSCOPE_API_KEY" not in fields and "ALIYUN_BASE_URL" not in fields)

print("\n=== 3b. 实际构造一次配置对象 ===")
try:
    c = VoyageConfig()
    check("配置对象可构造", True)
    check("OpenCode 通道有值（真正使用的）",
          bool(c.OPENCODE_GO_URL) and bool(c.OPENCODE_API_KEY))
except Exception as e:  # noqa: BLE001
    check("配置对象可构造", False, f"{type(e).__name__}: {e}")

print("\n=== 4. .env 里遗留的旧键不应导致启动失败 ===")
env_keys = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=",
                          Path(".env").read_text(encoding="utf-8"), re.M))
declared_raw = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*:", cfg_src, re.M))
# 比较必须**大小写不敏感**：config 设了 case_sensitive=False，
# 故 .env 里的 OpenCode_API_KEY 与声明的 OPENCODE_API_KEY 是同一个字段。
# （上一版用大小写敏感的集合差集，把这种正常写法误判成「未声明」。）
declared = {k.upper() for k in declared_raw}
leftover = sorted(k for k in env_keys if k.upper() not in declared)
print(f"  .env 中不被 config 读取的键（会被忽略）: {leftover or '无'}")

# extra="ignore" 是这里的关键：默认的 extra="forbid" 会让上面这些多余键
# 直接抛 ValidationError，服务根本起不来。
check("已显式设置 extra='ignore'", 'extra="ignore"' in cfg_src or "extra='ignore'" in cfg_src)
try:
    VoyageConfig()
    check("带遗留键的 .env 仍能加载", True, f"遗留键 {leftover}")
except Exception as e:  # noqa: BLE001
    check("带遗留键的 .env 仍能加载", False, f"{type(e).__name__}: {e}")

required = {k for k, f in fields.items() if f.is_required()}
missing = sorted(k for k in required if k not in {e.upper() for e in env_keys})
check("没有「必填但 .env 未提供」的键", not missing, str(missing))

print("\n=== 5. 应用可正常导入（启动第一步）===")
try:
    import app.main  # noqa: F401

    check("import app.main 成功", True)
except Exception as e:  # noqa: BLE001
    check("import app.main 成功", False, f"{type(e).__name__}: {e}")

print(f"\n{'=' * 56}\n配置清理验证: {ok} 通过 / {bad} 失败\n{'=' * 56}")
sys.exit(1 if bad else 0)
