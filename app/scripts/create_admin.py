"""幂等创建/提升管理员账号。

用法：
    uv run python app/scripts/create_admin.py --email admin@example.com
    uv run python app/scripts/create_admin.py --email a@b.com --username admin --password-env ADMIN_PASSWORD
    uv run python app/scripts/create_admin.py --email a@b.com --dry-run

与「首个注册用户成为管理员」的关系：
- 常规部署不再需要本脚本：库为空时，第一个通过页面注册的用户会自动
  成为管理员（见 app/modules/user/service.py 的 to_register）。
  该引导是一次性的，一旦有人注册即永久关闭。
- 本脚本用于**引导之外的场景**：首个账号权限丢失、需要额外增设管理员、
  或部署方希望完全跳过引导流程直接指定账号。
- 两条途径可以共存：脚本提升的是指定邮箱，与「谁是第一个」无关。

设计取舍：
- 幂等：重复执行只做「确保该邮箱是启用的管理员」，不重置密码、不报错。
- 密码只接受交互输入或环境变量，不接受 --password 明文参数（避免进入
  shell 历史与进程列表）。
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

# 允许以文件路径直接执行：uv run python app/scripts/create_admin.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from app.modules.user.auth import PasswordManager, validate_password_strength
from app.modules.user.constants import ROLE_SUPER_ADMIN, VALID_ROLES
from app.shared.db import AsyncSessionLocal, engine
from app.shared.db.models import User


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="create_admin", description="幂等创建或提升管理员账号")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument("--username", help="用户不存在时新建所需的昵称（2-10 字）")
    parser.add_argument("--password-env", help="从该环境变量读取新建账号的密码；不传则交互式输入")
    parser.add_argument(
        "--role",
        default=ROLE_SUPER_ADMIN,
        choices=sorted(VALID_ROLES),
        help=(
            "目标角色，默认 super_admin。"
            "super_admin=可读写后台；admin=普通管理员，只能查看数据不能操作。"
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查将要执行的动作，不写库")
    return parser.parse_args()


def _read_password(args: argparse.Namespace) -> str:
    if args.password_env:
        value = os.environ.get(args.password_env)
        if not value:
            raise SystemExit(f"环境变量 {args.password_env} 为空或未设置")
        return value
    first = getpass.getpass("请输入管理员密码: ")
    second = getpass.getpass("请再次输入以确认: ")
    if first != second:
        raise SystemExit("两次输入的密码不一致")
    return first


async def _run(args: argparse.Namespace) -> int:
    email = str(TypeAdapter(EmailStr).validate_python(args.email.strip()))

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if user is not None:
            if user.role == args.role and user.is_active:
                print(f"[skip] {email} 已是启用的 {args.role}（id={user.id}），无需变更")
                return 0
            print(
                f"[promote] 设为 {args.role}: {email} (id={user.id}) "
                f"role={user.role} -> {args.role}, is_active={user.is_active} -> True"
            )
            if args.dry_run:
                print("[dry-run] 未写库")
                return 0
            user.role = args.role
            user.is_active = True
            await session.commit()
            print(f"[done] {email} 现在是 {args.role}")
            return 0

        if not args.username:
            raise SystemExit(
                f"用户 {email} 不存在。新建账号需要提供 --username（昵称，2-10 字）。"
            )
        username = args.username.strip()
        if not 2 <= len(username) <= 10:
            raise SystemExit("昵称长度需在 2-10 个字符之间")

        # dry-run 必须在读取密码之前返回，否则会卡在交互式输入上
        print(f"[create] 新建管理员: {email} (username={username})")
        if args.dry_run:
            print("[dry-run] 未写库（跳过密码输入）")
            return 0

        password = _read_password(args)
        try:
            validate_password_strength(password)
        except Exception as exc:  
            raise SystemExit(f"密码强度不足: {exc}") from exc

        session.add(
            User(
                email=email,
                username=username,
                password=PasswordManager.hash(password),
                role=args.role,
                is_active=True,
            )
        )
        await session.commit()
        print(f"[done] {args.role} {email} 创建完成")
        return 0


async def main() -> int:
    args = _parse_args()
    try:
        return await _run(args)
    except ValidationError as exc:
        raise SystemExit(f"邮箱格式不合法: {args.email}") from exc
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
