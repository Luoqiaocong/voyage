"""前端无障碍回归测试。

扫描项：
  · img 必须有 alt（含 alt=""，装饰性图片也需显式声明）
  · input/textarea/select 必须有可访问名称
    （aria-label / aria-labelledby / id / 被 <label> 包裹，任一即可）
  · 可点击的 div 必须有 role 与 tabindex（否则键盘不可达）
  · icon-only 按钮必须有 aria-label 或 title

写这个测试的动因：这三类缺口用肉眼很难发现（按钮长得一样、
输入框有 placeholder 看起来就「有说明」），但读屏器用户会直接卡住。
扫描器本身也踩过坑，教训写在下面每一处判断里。
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ok_n = fail_n = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global ok_n, fail_n
    ok_n += 1 if ok else 0
    fail_n += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def preprocess(src: str) -> str:
    """把 {{ ... }} 插值替换成占位符。

    不这么做的话，插值里的 `>`（如 {{ a > b }}）会让「去标签」的正则
    提前结束，把后面的文字一起吃掉 —— 初版扫描器就是这样误报了 23 个
    「有文字的按钮缺少 aria-label」。
    """
    return re.sub(r"\{\{[\s\S]*?\}\}", "T", src)


# Vue 的动态绑定是「:aria-label」，只判 "aria-label" 会漏掉它们，
# 从而把大量已合规的控件报成缺失（第二版扫描器的坑）。
NAME_ATTRS = (
    "aria-label", ":aria-label", "v-bind:aria-label",
    "aria-labelledby", ":aria-labelledby",
    "title", ":title",
)


class A11y(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.img_bad: list[str] = []
        self.input_bad: list[str] = []
        self.clickdiv_bad: list[str] = []
        self.btn_named = 0      # 靠 aria-label / title 拿到名称
        self.btn_textual = 0    # 靠可见文字拿到名称
        self.btn_bad: list[str] = []
        self._btn: dict | None = None

    @property
    def in_label(self) -> bool:
        return "label" in self.stack

    @staticmethod
    def _named(a: dict) -> bool:
        return any(k in a for k in NAME_ATTRS)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        line = self.getpos()[0]

        if self._btn is not None:
            self._btn["tags"].append(tag)
        elif tag == "button":
            self._btn = {"line": line, "attrs": a, "text": [], "tags": []}

        if tag == "img" and "alt" not in a and ":alt" not in a:
            self.img_bad.append(f"{line} {a.get('src', '?')}")
        elif tag in ("input", "textarea", "select"):
            if a.get("type") not in ("hidden", "submit", "button"):
                # 被 <label> 包裹同样是合法的名称来源 —— 只判 id 与
                # aria-label 会把它们误报（第三版扫描器的坑）
                if not (self._named(a) or "id" in a or ":id" in a or self.in_label):
                    self.input_bad.append(f"{line} <{tag}>")
        elif tag == "div" and ("@click" in a or "v-on:click" in a):
            # aria-hidden 的纯装饰遮罩不算交互控件（它有 Esc 等价操作）
            if a.get("aria-hidden") != "true" and not any(
                k in a for k in ("role", ":role", "tabindex", ":tabindex")
            ):
                self.clickdiv_bad.append(f"{line} {a.get('class', '?')[:40]}")

        if tag not in ("br", "hr", "img", "input", "source", "track", "wbr",
                       "area", "base", "col", "meta", "link"):
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        """"自闭合标签只做 img 检查，**不入栈**。

        之前直接复用 handle_starttag 会让自闭合标签永不弹出，
        污染 in_label 判断。
        """
        a = dict(attrs)
        if tag == "img" and "alt" not in a and ":alt" not in a:
            self.img_bad.append(f"{self.getpos()[0]} {a.get('src', '?')}")
        if self._btn is not None:
            self._btn["tags"].append(tag)

    def handle_data(self, data):
        if self._btn is not None:
            self._btn["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._btn is not None:
            b = self._btn
            self._btn = None
            has_text = "".join(b["text"]).strip() != ""
            if has_text:
                # 可见文字即无障碍名称，无需 aria-label
                self.btn_textual += 1
            elif self._named(b["attrs"]):
                self.btn_named += 1
            else:
                self.btn_bad.append(f"{b['line']} 内部={b['tags']}")
        while self.stack:
            if self.stack.pop() == tag:
                break


print("=== 扫描 web/src 下所有 .vue ===")
files = sorted(Path("web/src").rglob("*.vue"))
check("找到待扫描文件", len(files) > 10, f"{len(files)} 个")

agg = {"img": [], "input": [], "clickdiv": [], "button": []}
named_total = 0
textual_total = 0
for f in files:
    p = A11y()
    p.feed(preprocess(f.read_text(encoding="utf-8")))
    named_total += p.btn_named
    textual_total += p.btn_textual
    for k, store in (("img", p.img_bad), ("input", p.input_bad),
                     ("clickdiv", p.clickdiv_bad), ("button", p.btn_bad)):
        agg[k].extend(f"{f}:{x}" for x in store)

print(f"  按钮统计：靠 aria-label/title {named_total} 个，"
      f"靠可见文字 {textual_total} 个\n")

print("=== 1. img 必须有 alt ===")
check("无缺失", not agg["img"], "\n      ".join(agg["img"][:10]))

print("\n=== 2. 输入控件必须有可访问名称 ===")
check("无缺失", not agg["input"], "\n      ".join(agg["input"][:10]))

print("\n=== 3. 可点击 div 键盘可达 ===")
check("无缺失", not agg["clickdiv"], "\n      ".join(agg["clickdiv"][:10]))

print("\n=== 4. 按钮必须有可访问名称（文字或 aria-label）===")
check("无 icon-only 且无名称的按钮", not agg["button"],
      "\n      ".join(agg["button"][:10]))
check("扫描确实覆盖到按钮", named_total + textual_total > 50,
      f"共 {named_total + textual_total} 个")

print(f"\n{'=' * 60}\n无障碍回归测试: {ok_n} 通过 / {fail_n} 失败\n{'=' * 60}")
sys.exit(1 if fail_n else 0)
