"""记忆提炼的 schema 与提示词。

记忆的「键空间」是刻意收窄的：只提炼**稳定且对后续规划有用**的事实。
不提炼一次性信息（"明天想去故宫"），因为它们很快就过期，注入反倒干扰。
"""
from pydantic import BaseModel, Field

# 允许出现的键白名单。
#
# 为什么用白名单而不是让模型自由发挥：
#   键若不收敛，同一件事会被写成 "budget" / "budget_level" / "预算档位"，
#   冲突消解就失效了（它们被当成不同事实各存一条）。
#   白名单让"同 key 覆盖"这条规则真正生效。
SCALAR_KEYS = frozenset({
    "budget_level",   # 预算档位：穷游/经济/舒适/奢华
    "travel_pace",    # 行程节奏：紧凑/适中/悠闲
    "home_city",      # 常住城市（影响出发地交通建议）
})

MULTI_KEYS = frozenset({
    "preference",       # 旅行偏好：美食/摄影/自然风光/历史文化…
    "dietary",          # 饮食禁忌或偏好：素食/不吃辣/清真…
    "visited_city",     # 已去过的城市（避免重复推荐）
    "companion",        # 同行人类别：亲子/老人/情侣/独自
})

ALLOWED_KEYS = SCALAR_KEYS | MULTI_KEYS

# 各键的合法取值（仅对取值有限的键约束；其余为自由文本）
VALUE_ENUMS: dict[str, set[str]] = {
    "budget_level": {"穷游", "经济", "舒适", "奢华"},
    "travel_pace": {"紧凑", "适中", "悠闲"},
}

# 键 → 中文标签。放在 schemas 而非 service：注入 prompt 与前端展示都要用，
# 属于两处共享的展示映射，放这里避免 service ↔ router 互相导入。
KEY_LABELS: dict[str, str] = {
    "budget_level": "预算档位",
    "travel_pace": "行程节奏",
    "home_city": "常住城市",
    "preference": "旅行偏好",
    "dietary": "饮食禁忌",
    "visited_city": "去过的城市",
    "companion": "同行人",
}

# 置信度：用户明确表述 vs 模型推断。阈值用于注入时的排序与过滤。
CONFIDENCE_EXPLICIT = 0.9   # 用户直接说"我预算有限"
CONFIDENCE_INFERRED = 0.6   # 从上下文推断（如频繁问便宜青旅 → 穷游）


class MemoryFact(BaseModel):
    """从对话中提炼出的单条事实。"""

    fact_key: str = Field(
        description=(
            "事实键，必须从下列白名单中选择："
            "预算档位=budget_level，行程节奏=travel_pace，常住城市=home_city，"
            "旅行偏好=preference，饮食禁忌=dietary，去过的城市=visited_city，"
            "同行人=companion。不要自创键名。"
        )
    )
    fact_value: str = Field(
        description=(
            "事实取值，简短明确（不超过 20 字）。"
            "budget_level 只能是 穷游/经济/舒适/奢华 之一；"
            "travel_pace 只能是 紧凑/适中/悠闲 之一；"
            "visited_city 写城市名；preference/dietary/companion 写简短标签。"
        )
    )
    confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description=(
            "置信度：用户在对话中明确陈述的取 0.9；由行为或偏好间接推断的取 0.6 以下。"
        ),
    )
    evidence: str = Field(
        description="支撑该事实的原文片段（不超过 50 字），用于人工核对提炼是否准确。"
    )


class MemoryExtraction(BaseModel):
    """一次提炼的完整结果。"""

    facts: list[MemoryFact] = Field(
        default_factory=list,
        description=(
            "本次对话中提炼出的稳定事实列表。"
            "若对话中没有值得长期记住的信息（如纯闲聊、一次性询问），返回空列表。"
            "宁缺毋滥：不确定的信息不要提取。"
        ),
    )


MEMORY_SYSTEM_PROMPT = (
    "你是一个用户画像提炼助手。请从给定的对话内容中，提炼出**值得长期记住**的稳定事实。\n"
    "\n"
    "提炼原则：\n"
    "1. 只提取稳定偏好与属性（预算观念、旅行节奏、饮食禁忌、常去城市、同行人类别、兴趣偏好）。\n"
    "2. 不要提取一次性信息：具体的某次日期、某个临时需求、单次查询内容。\n"
    "3. 宁缺毋滥：没有把握就不要提取。宁可返回空列表，也不要编造。\n"
    "4. 取值要简短（不超过 20 字），用标签式表达而非整句。\n"
    "5. 必须给出原文依据（evidence），不得凭空推测。\n"
    "\n"
    "注意：只输出符合 Schema 的 JSON，不要额外解释。"
)
