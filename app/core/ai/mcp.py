import asyncio
import os
import sys

from langchain.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.shared.utils import log

# ===================== 1. MCP 配置字典 =====================
#
# 关于 duckduckgo-mcp-server 的启动命令：
#
# 它是本配置里**唯一走 stdio 传输**的 MCP，其余都是远程 streamable_http
# （与平台无关）。stdio 需要我们自己拉起子进程，命令就与操作系统绑定了：
#
#   Windows  必须经 cmd 才能解析并执行 uvx（uvx 是控制台脚本，非可执行文件）
#   Linux    直接调用 uvx 即可；写 cmd 会因找不到该命令而启动失败
#
# 两个平台的命令都必须正确，否则这个 MCP 起不来；而失败是静默降级
# （见 get_namespace_tools 的兜底），表现为 travel 子 Agent 少了一组
# 网页搜索工具，不易察觉。
#
# 版本固定而不是交给 uvx 取最新：
#   - uvx 默认拉 PyPI 最新版，上游发新版可能改变工具签名，而我们的
#     依赖声明里没有它（它不由 uv.lock 管理），等于埋了个会自己变的依赖
#   - 首次运行需联网下载，固定版本让"下载到哪一个"可预期
_IS_WINDOWS = sys.platform == "win32"

#: uvx 启动 duckduckgo-mcp-server 的命令（按平台生成）
_UVX_CMD = ["cmd", "/c", "uvx"] if _IS_WINDOWS else ["uvx"]

#: 包与版本。默认值供本地开发直接使用；Docker 构建时通过同名环境变量注入，
#: 使「构建期预热下载的版本」与「运行期实际拉起的版本」必然一致 ——
#: 若两边各写一个版本号，很容易出现装了 A 版却拉起 B 版。
#:
#: 关于版本选择：0.7.0 是写作时的最新版（PyPI 上另有 0.1.0~0.1.2 与 0.3.0+，
#: 中间跳过了 0.2.x）。**改版本前务必先确认该版本存在**，
#: 否则 uvx 会因找不到版本而启动失败，且失败是静默降级、不易发现。
_DDG_MCP_PACKAGE = os.getenv("DDG_MCP_PACKAGE", "duckduckgo-mcp-server==0.7.0")

MCPCONFIG = {
    "TICKET_TOOLS_CONFIG": {
        "12306-mcp": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/61b1655c916844/mcp",
        },
    },
    "WEATHER_TOOLS_CONFIG": {
        "Weather-service": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/aa891a32a54645/mcp",
        },
    },
    "TRAVEL_TOOLS_CONFIG": {
        "duckduckgo-mcp-server": {
            "transport": "stdio",
            "command": _UVX_CMD[0],
            "args": [*_UVX_CMD[1:], _DDG_MCP_PACKAGE],
            "env": {**os.environ},
        },
        "AI_Go_Hotel_MCP": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/77461314a7b246/mcp",
        },
        "hotel-recommend": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/435a851e7af345/mcp",
        },
        "travel_food": {
            "transport": "streamable_http",
            "url": "https://mcp.api-inference.modelscope.net/cca0e88b098e43/mcp",
        },
    },
}

# ===================== 2. 命名空间映射 =====================
NAMESPACE_MEMO = {
    "ticket": "TICKET_TOOLS_CONFIG",
    "weather": "WEATHER_TOOLS_CONFIG",
    "travel": "TRAVEL_TOOLS_CONFIG",
}

# ===================== 3. Client 缓存与工具获取 =====================
# 缓存已初始化的 Client 实例，避免重复建连和资源泄漏
_clients_cache: dict[str, MultiServerMCPClient] = {}

#: 已经取过工具的 namespace，用来区分「冷启动」与「运行期」。
#: 两者的合理超时差一个数量级（见下），故必须分开。
_warmed_namespaces: set[str] = set()

#: 冷启动超时。首次拉取要额外承担两件事：
#:   1. 通过 uvx 下载 duckduckgo-mcp-server（首次运行没有本地缓存）
#:   2. 与 PostgreSQL checkpointer、Redis 的初始化争 CPU
#: 故必须给足余量：一旦判超时，travel 子 Agent 会静默降级为 0 个工具，
#: 用户侧表现为「搜索 / 酒店 / 美食推荐没有数据」。
COLD_START_TIMEOUT_SECONDS = 45.0

#: 运行期超时。此时连接已建立、包已缓存，仍保留较短的超时，
#: 避免某个 MCP 端点变慢时把用户请求一起拖住。
TOOL_FETCH_TIMEOUT_SECONDS = 10.0


async def get_namespace_tools(namespace: str) -> list[BaseTool]:
    """
    根据命名空间获取对应的 MCP 工具列表（带超时与降级）。
    自动缓存 MultiServerMCPClient 实例以复用连接；拉取失败返回空列表，
    由子 Agent 提示词的兜底话术接管应答，不让单个 MCP 端点卡死整个请求。

    超时分两档：该 namespace **第一次取用时给冷启动超时**，成功之后回到
    运行期超时。冷启动慢是正常的（下载 + 初始化争抢），不该因此判失败；
    但也不能一直用长超时，否则运行期某个端点卡住会把请求拖很久。
    """
    # 1. 查映射表
    config_key = NAMESPACE_MEMO.get(namespace)
    if not config_key:
        valid_keys = ", ".join(NAMESPACE_MEMO.keys())
        raise ValueError(f"未知的 namespace '{namespace}'，有效值为: {valid_keys}")

    # 2. 取出对应的配置字典
    tools_config = MCPCONFIG.get(config_key, {})
    if not tools_config:
        return []

    # 3. 复用或创建 Client 实例，整体限时拉取工具
    cold = namespace not in _warmed_namespaces
    timeout = COLD_START_TIMEOUT_SECONDS if cold else TOOL_FETCH_TIMEOUT_SECONDS
    try:
        if namespace not in _clients_cache:
            _clients_cache[namespace] = MultiServerMCPClient(tools_config)

        tools = await asyncio.wait_for(
            _clients_cache[namespace].get_tools(),
            timeout=timeout,
        )
        _warmed_namespaces.add(namespace)
        log.info(
            f"[mcp] namespace '{namespace}' 工具就绪：{len(tools)} 个"
            + ("（冷启动）" if cold else "")
        )
        return tools
    except Exception as exc:  # noqa: BLE001 - 统一降级入口，避免单个 MCP 端点拖垮请求
        # 降级：丢弃失败缓存，返回空工具列表（子 Agent 兜底话术接管）
        _clients_cache.pop(namespace, None)
        # 超时后也标记为已预热：此时 uvx 多半已把包装好，
        # 下一次用短超时重试即可；否则会永远享受 45s 长超时，失去运行期保护。
        _warmed_namespaces.add(namespace)
        log.error(
            f"[mcp] namespace '{namespace}' 不可用"
            f"（{'冷启动' if cold else '运行期'}，超时 {timeout:.0f}s）：{exc}"
        )
        return []
