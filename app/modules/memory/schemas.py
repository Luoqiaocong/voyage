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

# 各键的合法取值。
#
# 原本只有 budget_level 与 travel_pace 有约束，其余是自由文本 ——
# 实测这直接导致了重复：同一件事被写成不同措辞就各存一条，
# 例如 companion 同时出现「朋友」与「两人同行」。
#
# 修法不是把自由文本也变成严格枚举（那样会丢掉表达力，比如 dietary
# 有无数种禁忌组合），而是**给出推荐词表**：提示词要求模型优先从词表里选，
# 使绝大多数取值收敛到同一套标签；词表之外的值依然允许，
# 由 service 层的宽松去重兜底。
VALUE_ENUMS: dict[str, set[str]] = {
    "budget_level": {"穷游", "经济", "舒适", "奢华"},
    "travel_pace": {"紧凑", "适中", "悠闲"},
    "companion": {"独自", "情侣", "朋友", "亲子", "父母", "同事", "团队"},
    "dietary": {"素食", "不吃辣", "不吃海鲜", "清真", "忌口较多", "无特殊要求"},
}

# 每个键的推荐词表（用于生成提示词；VALUE_ENUMS 是其子集）
RECOMMENDED_VALUES: dict[str, tuple[str, ...]] = {
    **{k: tuple(sorted(v)) for k, v in VALUE_ENUMS.items()},
    "preference": (
        "美食", "自然风光", "历史文化", "博物馆", "摄影", "户外徒步",
        "购物", "夜生活", "小众冷门", "亲子友好", "休闲度假", "文艺",
    ),
    "visited_city": (),   # 城市名无法枚举，靠「一城一条 + 宽松去重」保证
    "home_city": (),
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
    "4. 必须给出原文依据（evidence），不得凭空推测。\n"
    "\n"
    "【最重要的一条：一个取值只放一件事】\n"
    "fact_value 必须是**单个**取值，不得用「、」「,」「和」「与」把多项拼在一起。\n"
    "正确：用户去过北京、上海、广州 → 输出 3 条 visited_city 事实，"
    "分别是「北京」「上海」「广州」。\n"
    "错误：输出 1 条 visited_city = 「北京、上海、广州」。\n"
    "同理，喜欢美食与摄影 → 输出 2 条 preference 事实。\n"
    "原因：拼在一起的取值无法与其它记录比对，会导致同一件事被重复记住。\n"
    "\n"
    "【取值请优先使用下列标准标签】\n"
    "- budget_level：穷游 / 经济 / 舒适 / 奢华\n"
    "- travel_pace：紧凑 / 适中 / 悠闲\n"
    "- companion：独自 / 情侣 / 朋友 / 亲子 / 父母 / 同事 / 团队\n"
    "  （注意：「两人同行」应写成「情侣」或「朋友」，按语境选最贴切的那个）\n"
    "- dietary：素食 / 不吃辣 / 不吃海鲜 / 清真 / 忌口较多 / 无特殊要求\n"
    "- preference：美食 / 自然风光 / 历史文化 / 博物馆 / 摄影 / 户外徒步 /\n"
    "  购物 / 夜生活 / 小众冷门 / 亲子友好 / 休闲度假 / 文艺\n"
    "- visited_city：只写城市名本身，不带省份、不带修饰（写「北京」而不是「北京市」）\n"
    "\n"
    "若某项事实确实无法归入上面的标签，可以自拟简短标签，但仍须遵守「一个取值一件事」。\n"
    "\n"
    "注意：只输出符合 Schema 的 JSON，不要额外解释。"
)
