"""前端 .vue 文件的结构校验（SFC 模板嵌套）。

## 为什么需要它

`vue-tsc --noEmit` 只做类型检查，**不校验模板标签嵌套**。
实测教训：MemoryPanel.vue 曾带着「Invalid end tag」被提交并通过了
tsc 与后端全部脚本，直到 Vite dev server 报错才暴露 —— 页面直接打不开。

所以用一个独立脚本调用 Vue 官方编译器（与 Vite 用的同一个）
把每个 .vue 解析一遍，把这类错误挡在提交之前。

## 用法

    uv run --no-sync python tests/test_vue_sfc.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
WEB = ROOT / "web"
SRC = WEB / "src"

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


JS = r"""
const fs = require('fs');
const { parse } = require('@vue/compiler-sfc');
const files = process.argv.slice(2);
const out = {};
for (const f of files) {
  const { errors } = parse(fs.readFileSync(f, 'utf8'), { filename: f });
  out[f] = errors.map((e) => {
    const l = (e.loc && e.loc.start) || {};
    return (l.line || 0) + ':' + (l.column || 0) + ' ' + (e.message || e);
  });
}
console.log(JSON.stringify(out));
"""


def main() -> int:
    print("=== 1. 运行环境 ===")
    if shutil.which("node") is None:
        print("  未找到 node，跳过")
        return 0
    compiler = WEB / "node_modules" / "@vue" / "compiler-sfc"
    if not compiler.exists():
        print("  未找到 @vue/compiler-sfc，跳过（先在前端目录安装依赖）")
        return 0
    print("  node 与 @vue/compiler-sfc 均可用")

    print("\n=== 2. 收集 .vue 文件 ===")
    files = sorted(SRC.rglob("*.vue"))
    check(f"找到 {len(files)} 个 .vue 文件", len(files) > 0, str(len(files)))
    if not files:
        return 1

    print("\n=== 3. 用 Vue 官方编译器逐个校验 ===")
    helper = WEB / ".sfc_check_tmp.cjs"
    helper.write_text(JS, encoding="utf-8")
    try:
        res = subprocess.run(
            ["node", str(helper)] + [str(f) for f in files],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(WEB),
        )
    finally:
        helper.unlink(missing_ok=True)

    raw = (res.stdout or "").strip()
    if not raw:
        check("编译器有输出", False, (res.stderr or "")[:300])
        return 1
    result = json.loads(raw)

    bad: dict[str, list[str]] = {}
    for f, errs in result.items():
        if errs:
            bad[f] = errs

    if bad:
        for f, errs in sorted(bad.items()):
            rel = Path(f).relative_to(ROOT)
            print(f"    ✗ {rel}")
            for e in errs[:4]:
                print(f"        {e[:140]}")
    check("所有 .vue 模板结构合法", not bad, f"{len(bad)} 个文件有错误" if bad else "")

    print(f"\n{'=' * 56}\nSFC 结构校验: {ok_n} 通过 / {fail_n} 失败\n{'=' * 56}")
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
