from datetime import datetime, timezone

# ── ORM 语法基础（建议记牢）────────────────────────────────────
# Mapped[str]      : 类型标注，配合下方 mapped_column 声明列的类型
# mapped_column(...): 真正定义“这一列”的属性（类型/约束/索引等）
# ForeignKey       : 外键，建立表关联（如 conversations.user_id → users.id）
# relationship     : ORM 层的“对象关系”，用于 Python 侧便捷访问关联数据
#                    （它只影响 ORM 对象访问，不影响数据库表结构本身）
# ────────────────────────────────────────────────────────────────
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def utc_now():
    """返回当前 UTC 时间（供 default 使用）"""
    return datetime.now(timezone.utc)


class User(Base):
    """用户表。"""
    __tablename__ = "users"   # 数据库表名（不然会用类名默认）

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="用户ID")
    
    email: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True, comment="用户邮箱")
    
    username: Mapped[str] = mapped_column(
            String(64), index=True, nullable=False
        )
    
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        String(16),
        default="user",
        nullable=False,
        index=True,
        comment="角色：user=普通用户，admin=管理员（管理端接口的鉴权依据）",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用：被禁用的用户无法登录，但数据保留",
    )

    avatar: Mapped[str] = mapped_column(
        String(255),
        default="photographer.png",
        comment="头像文件名（不含域名，如 photographer.png）"
    )

    # relationship : 让 Python 侧能用 user.conversations 拿到该用户的所有会话
    # back_populates: 关联到 Conversation.user，二者互为反向
    # cascade       : 删用户时级联删其会话(all, delete-orphan)
    created_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
            default=utc_now,
            nullable=False,
            comment="创建时间（UTC）",
        )
   
    conversations: Mapped[list["Conversation"]] = relationship(
           back_populates="user", # 双向关系的另一侧：在 Conversation 模型中，对应的属性叫 user
           cascade="all, delete-orphan",
       )


class Conversation(Base):
    """会话表：让会话有归属（user_id）——解决"会话无法校验存在性"的缺口。"""
    __tablename__ = "conversations"

    # id 沿用现有 12 位 hex conversation_id
    id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="会话ID")
    # 用 conversation_id 作主键 → 可以用 SELECT...WHERE id=? 判断“存不存在”
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="用户ID",
    )
    # ForeignKey("users.id") : 外键指向 users 表的 id 列
    # ondelete="CASCADE"     : 用户在数据库层删除时，其会话也级联删除
    # index=True             : 按 user 查会话更快
    title: Mapped[str | None] = mapped_column(String(255), nullable=True,comment="会话标题")
    # str | None + nullable=True：该列允许 NULL（会话标题可空）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        comment="会话创建时间（UTC）",
    )
    
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="会话消息数",
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    
    itineraries: Mapped[list["Itinerary"]] = relationship(
        back_populates="conversation", # 双向关系的另一侧：在 Itinerary 模型中，对应的属性叫 conversation
        passive_deletes=True,  # 删除时由数据库处理关联，SQLAlchemy 不额外查询
    )
    # 一个会话可保存多份行程；删除会话不影响已保存的行程（行程是用户资产）


class Itinerary(Base):
    """行程表：一次「保存」的完整行程计划，plan 列存 ItineraryPlan 的 JSON。"""
    __tablename__ = "itineraries"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="行程ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属用户ID（行程独立归属用户，删除用户时级联删除）",
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="来源会话ID（12位hex）；会话删除后置空，行程保留",
    )
    plan: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="行程计划 JSON（ItineraryPlan：destination/days/daily_plans/tips 等）",
    )
    created_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        comment="创建时间（UTC）",
    )
    updated_at: Mapped[datetime] = mapped_column(
         DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        comment="更新时间（UTC），保存后再次编辑时自动刷新",
    )

    conversation: Mapped[Conversation | None] = relationship(back_populates="itineraries")

    # 一份行程可创建多个分享链接（不同权限 / 发给不同的人），故为一对多。
    # cascade 让行程删除时分享链接一并清除，避免留下指向空行程的僵尸链接。
    shares: Mapped[list["ItineraryShare"]] = relationship(
        back_populates="itinerary", cascade="all, delete-orphan"
    )


class TokenUsage(Base):
    """LLM 用量按「模型 + 日期」聚合成一行。

    由 app/shared/usage.py 的后台任务从 Redis 增量合并写入；
    同一 (model, record_date) 重复落库时为累加而非覆盖（见唯一约束）。
    """

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    model: Mapped[str] = mapped_column(String(50), index=True, comment="模型 ID")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入 token 数")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输出 token 数")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="总 token 数")
    calls: Mapped[int] = mapped_column(Integer, default=0, comment="LLM 调用次数")
    record_date: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True, comment="统计日期 yyyy-MM-dd（本地时区）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, comment="创建时间（UTC）"
    )
    __table_args__ = (UniqueConstraint("model", "record_date", name="uq_model_date"),)


class UserTokenUsage(Base):
    """LLM 用量按「用户 + 日期」聚合成一行。

    ## 为什么单独一张表，而不是给 token_usage 加一列 user_id

    两者是**不同的聚合维度**，不是同一张表能自然承载的：
      · token_usage     按「模型 × 日期」——回答「哪个模型花得多」
      · user_token_usage 按「用户 × 日期」——回答「谁用得最多」
    若合并成一张表，唯一键会变成 (user, model, date)，其中 user_id 必须允许为空
    （模型维度的行不属于任何用户），一个可空列参与唯一约束会让
    upsert 的「冲突即累加」语义变得难以推理；而且现有看板的所有聚合查询
    都要跟着改，回归风险不小。

    分成两张表后：现有链路完全不动，新增的这张只负责用户维度。
    代价是同一次调用要向两处各累加一次（写入是 Redis 内的，成本可忽略）。

    ## 历史数据

    本表从引入时开始累积。token_usage 里已有的数据**没有用户维度**，
    无法拆分到用户，因此改造前的用量不会出现在用户排行里 —— 这是已知且
    无法弥补的缺失，不是 bug。
    """

    __tablename__ = "user_token_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属用户ID（用户注销时级联删除其用量记录）",
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入 token 数")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输出 token 数")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="总 token 数")
    calls: Mapped[int] = mapped_column(Integer, default=0, comment="LLM 调用次数")
    record_date: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True, comment="统计日期 yyyy-MM-dd（本地时区）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, comment="创建时间（UTC）"
    )
    __table_args__ = (
        UniqueConstraint("user_id", "record_date", name="uq_user_date"),
    )


class AdminAuditLog(Base):
    """管理端操作审计日志：谁、何时、对谁做了什么、改前改后是什么。

    只记录管理端的写操作。目标对象用 (target_type, target_id) 弱关联而非外键——
    被操作对象可能后续被删除，但审计记录必须保留。
    """

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    operator_id: Mapped[int] = mapped_column(
        Integer, index=True, nullable=False, comment="操作者用户ID"
    )
    operator_email: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="操作者邮箱（冗余存一份，便于追溯）"
    )
    action: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
        comment="动作标识，如 user.role.update / user.status.update",
    )
    target_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="目标类型，如 user"
    )
    target_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="目标标识（用户ID等，字符串存储以兼容多种主键）"
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="变更明细（JSON 字符串：改前/改后）"
    )
    ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="来源 IP"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False,
        comment="操作时间（UTC）",
    )


class ItineraryShare(Base):
    """行程分享链接。

    设计要点
    --------
    - token 用 secrets.token_urlsafe(32) 生成，高熵不可猜；不直接暴露行程 ID。
    - 密码只存哈希（复用用户模块的 argon2 实现），绝不落明文；
      另设 password_plain 便于"再次查看"时回显，与 REFRESH_TOKEN 的既有做法一致。
      ⚠ 该字段是已知的明文存储弱点，若本项目进入真实生产环境应移除并改为只允许重置密码。
    - allow_copy / allow_edit 两个布尔位而非单一枚举：
      "可复制但不可改" 与 "可改" 是正交的，用位组合更自然。
    - 所有人用 owner_id 冗余记录，便于"我分享出去的全部链接"一次性查询与撤销。
    """

    __tablename__ = "itinerary_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    itinerary_id: Mapped[int] = mapped_column(
        ForeignKey("itineraries.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="被分享的行程ID（行程删除时级联删除分享）",
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="分享创建者ID（冗余记录，便于按用户批量查询与撤销）",
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False, comment="分享令牌（URL 安全随机串）"
    )
    allow_copy: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否允许访问者复制行程到自己的账号"
    )
    allow_edit: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否允许访问者直接编辑行程"
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="访问密码哈希（argon2）；为空表示无需密码"
    )
    password_plain: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="访问密码明文（便于分享者再次查看）"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="过期时间（UTC）；为空表示永不过期"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="撤销时间（UTC）；非空表示已失效"
    )
    view_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="访问次数"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, comment="创建时间（UTC）"
    )

    itinerary: Mapped["Itinerary"] = relationship(back_populates="shares")


class UserMemory(Base):
    """用户长期记忆：从对话中提炼的稳定事实，供后续会话注入。

    为什么用 (fact_key, fact_value) 键值对而不是整块 JSON：
        偏好类事实（"美食"、"摄影"）本就允许多个并存，而标量属性
        （预算档位、常住城市）同一 key 只应有一个值。键值对让这两类语义
        自然统一——冲突消解退化为「同 key 覆盖 + 留痕」，无需为每条事实
        单独设计合并规则。

    为什么保留 previous_value：
        用户偏好会变（"这次想穷游"推翻了上次的"预算充足"）。直接覆盖会丢失
        演进过程，且万一提炼有误无法回滚。保留旧值既便于用户在管理页看到
        变化，也让误判可追溯。

    为什么存 confidence 与 evidence：
        记忆是从自然语言里推断出来的，可靠性有高有低。"用户明确说"
        与"模型猜测"应当区别对待——注入 prompt 时按 confidence 排序取前若干条，
        低置信度的记忆不会挤占上下文。evidence 保留原文片段，便于人工核对。
    """

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属用户ID（用户注销时级联删除记忆）",
    )
    fact_key: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="事实键：标量属性如 budget_level/home_city；多值偏好用 preference 等",
    )
    fact_value: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="事实取值（字符串统一表示，便于比较与展示）"
    )
    previous_value: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="被本次覆盖的旧值（仅标量键会用到），便于追溯偏好变化"
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=0.6, nullable=False,
        comment="置信度 0-1：用户明确表述取高值，模型推断取低值",
    )
    evidence: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="来源原文片段，便于人工核对提炼是否准确"
    )
    source_conversation_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="来源会话ID；会话删除后置空但记忆保留"
    )
    hit_count: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="被重复提取到的次数，越高说明越稳定"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True,
        comment="是否生效：用户可停用某条记忆而无需删除",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, comment="首次提取时间（UTC）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False,
        comment="最近一次提取/修改时间（UTC）",
    )

    __table_args__ = (
        # 唯一性建立在 (用户, 键, 值) 三元组上，而非仅 (用户, 键)。
        # 这样两类语义自动统一，无需在代码里特判：
        #   - 标量属性（budget_level）：换值时 fact_value 变了但 fact_key 相同，
        #     应用层按「同 key 覆盖」处理，只保留最新值；
        #   - 多值偏好（preference="美食" 与 preference="摄影"）：
        #     值不同即视为两条独立事实，各自保留。
        # 同时该约束天然去重：同一事实被反复提取到只会命中已有行，
        # 由应用层把 hit_count 加一。
        UniqueConstraint("user_id", "fact_key", "fact_value", name="uq_user_memory_fact"),
    )
