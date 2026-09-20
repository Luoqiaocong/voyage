import sys
from pathlib import Path
from loguru import logger
from app.config import config

# 文件日志初始化失败时置为 True，供导出后由调用方（或排查时）判断当前是否只有控制台输出
file_log_disabled = False


def init_log():
    """初始化日志系统。

    控制台输出是**必须成功**的（它是排查一切问题的最后一根线）；
    文件输出是**增强**，失败时降级而不是让服务起不来。

    为什么文件日志必须容错：
        docker-compose 把宿主机 ./data 以 bind mount 挂到容器 /app/data，
        该目录可能是 **root** 属主（Docker 创建挂载点时），
        而容器内进程以 UID 10001（非 root）运行，于是
        /app/data/output/logs 的 mkdir 会抛 PermissionError。
        该目录正是本函数要写的路径，且 init_log() 在 lifespan 启动阶段被调用 ——
        没有这层保护时，一个「日志目录不可写」的问题会让整个后端启动失败，
        表现成容器反复重启，而真正的原因（日志目录权限）完全看不出来。

    同类风险还包括：磁盘满、只读文件系统、LOG_SAVE_PATH 配了不可写的绝对路径。
    这些都不该阻断服务启动。
    """
    global file_log_disabled

    logger.remove()
    file_log_disabled = False

    logger.add(
        sys.stdout,
        level=config.LOG_LEVEL,
        format="<blue>{time:YYYY-MM-DD HH:mm:ss}</blue> | <level>{level: <8}</level> | <green>{name}</green>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )

    if not config.LOG_TO_FILE:
        return

    try:
        # 路径层数：本文件在 app/shared/utils/ 下，回到项目根需要 **4** 层 parent
        # （parent×1=app/shared/utils, ×2=app/shared, ×3=app, ×4=项目根）。
        #
        # 层数必须与 Dockerfile 创建的 /app/data/output/logs、以及 compose
        # 挂载的 ./data:/app/data 对齐：否则容器里的日志既不在数据卷里
        # （重建即丢），也不在 Dockerfile chown 过的目录里（授权等于白做）。
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "output" / config.LOG_SAVE_PATH
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "voyage.log",
            rotation="10 MB",
            retention="7 days",
            level=config.LOG_LEVEL,
            encoding="utf-8",
            enqueue=True
        )
    except Exception as exc:  # noqa: BLE001
        # 降级为「仅控制台」，并把原因说清楚（含可操作的修复提示）。
        # 用 warning 而不是 error：服务仍可用，只是没有文件日志。
        file_log_disabled = True
        logger.warning(
            "[log] 文件日志不可用，已降级为仅控制台输出："
            f"{type(exc).__name__}: {exc}"
        )
        logger.warning(
            "[log] 若是容器部署，通常是宿主机 ./data 目录属主不是容器内用户（UID 10001）。"
            "修复：在宿主机执行  sudo mkdir -p data && sudo chown -R 10001:10001 data"
        )


def close_log():
    """关闭日志系统（释放资源）。"""
    logger.remove()
    # 等待日志写入完成
    import time
    time.sleep(0.1)


log = logger
