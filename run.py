"""跨平台启动入口：确保事件循环与 psycopg 兼容。

为什么需要这个文件：
    langgraph 的 PostgreSQL checkpointer 走 psycopg，而 psycopg 的异步模式
    **不能用 ProactorEventLoop**，只能用 SelectorEventLoop。

    而 uvicorn 在 Windows 上的选择逻辑是：

        def asyncio_loop_factory(use_subprocess=False):
            if sys.platform == "win32" and not use_subprocess:
                return asyncio.ProactorEventLoop      # ← 默认拿到这个
            return asyncio.SelectorEventLoop

    也就是说直接 `uvicorn app.main:app` 在 Windows 上必然报：
        psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'
                                to run in async mode

    Linux/macOS 上默认就是 SelectorEventLoop，本文件不做任何特殊处理。

用法：
    python run.py                       # 开发（默认 8000，自动 reload）
    python run.py --port 9000           # 换端口
    python run.py --host 0.0.0.0        # 对外监听

注意：Windows 上开启 reload 时 uvicorn 传 use_subprocess=True，
本身就会拿到 SelectorEventLoop；本文件仍显式指定，避免依赖这一细节。
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 Voyage 后端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--no-reload", action="store_true", help="关闭热重载")
    args = parser.parse_args()

    import uvicorn

    # Windows 必须显式指定循环工厂，否则拿到 ProactorEventLoop，
    # psycopg checkpointer 会直接拒绝启动（原因见 app/loop.py）。
    # uvicorn 的 loop 参数支持「模块:属性」形式。
    loop = "app.loop:selector_loop_factory" if sys.platform == "win32" else "auto"

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        loop=loop,
    )


if __name__ == "__main__":
    main()
