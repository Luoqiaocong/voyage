"""Declarative Base：所有 ORM 模型的基类。

继承它的类会被 SQLAlchemy 自动转成表结构，并注册进 Base.metadata。
Base.metadata 正是 alembic env.py 里 target_metadata = Base.metadata 要读取的东西。
"""
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

#AsyncAttrs 可以让你在异步程序中能够按需懒加载数据
class Base(AsyncAttrs, DeclarativeBase):
    """所有 ORM 模型的基类。"""
