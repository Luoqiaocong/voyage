import sys
from pathlib import Path
from loguru import logger
from app.config import config

def init_log():
    """初始化日志系统。"""
    logger.remove()

    logger.add(
        sys.stdout,
        level=config.LOG_LEVEL,
        format="<blue>{time:YYYY-MM-DD HH:mm:ss}</blue> | <level>{level: <8}</level> | <green>{name}</green>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )

    if config.LOG_TO_FILE:
        log_dir = Path(__file__).parent.parent.parent /'data'/ 'output' / config.LOG_SAVE_PATH
        log_dir.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_dir / "voyage.log",
            rotation="10 MB",
            retention="7 days",
            level=config.LOG_LEVEL,
            encoding="utf-8",
            enqueue=True
        )
        
def close_log():
    """关闭日志系统（释放资源）。"""
    logger.remove()
    # 等待所有日志写入完成
    import time
    time.sleep(0.1)

log = logger