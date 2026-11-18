import argparse
import os
import re
import sys

# The ✅/❌ result banners cannot be encoded by a non-UTF-8 console (cp936 on a
# Chinese Windows install, for one), so every run died on a UnicodeEncodeError
# at the very last line -- the check's verdict never reached the caller, pass
# or fail. Mirrors core/console.py; skills run standalone from an arbitrary
# cwd, so they cannot import it.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def check_content(content: str) -> list[str]:
    """检查提交信息草案是否包含空内容、隐私泄露或格式问题。"""
    if not content or not content.strip():
        return ["提交信息内容为空"]

    errors: list[str] = []

    # 规则 1: 禁止本地绝对路径 (如 D:\..., C:/..., file:///..., /Users/..., /home/...)
    # 使用负向后顾避免把 https:// / http:// 中的 "s://" 误判为盘符路径。
    win_abs_pattern = r"(?<![a-zA-Z0-9_])[a-zA-Z]:[\\/][^\s\"'`<>|]*"
    unix_home_pattern = r"(?<![a-zA-Z0-9_.:])(?:/Users/|/home/)[^\s\"'`<>|]+"
    file_uri_pattern = r"file://[^\s\"'`<>|]+"
    leaked_paths = (
        re.findall(win_abs_pattern, content)
        + re.findall(unix_home_pattern, content)
        + re.findall(file_uri_pattern, content)
    )
    if leaked_paths:
        errors.append(f"发现本地绝对路径: {', '.join(leaked_paths)}")

    # 规则 2: 禁止 IDE 注入的 cci:// 引用
    if re.search(r"cci://[^\s)]*", content):
        errors.append("发现 IDE 注入的 cci:// 引用")

    # 规则 3: 禁止 Markdown 链接格式 [text](url)，防止路径关联
    if re.search(r"\[[^\]]+\]\([^)]+\)", content):
        errors.append("发现 Markdown 链接格式，请保持纯文本")

    return errors


def _read_stdin_utf8() -> str:
    if hasattr(sys.stdin, "buffer"):
        return sys.stdin.buffer.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="审计 Git 提交信息草案，检测本地绝对路径、cci:// 引用和 Markdown 链接。"
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="file_path",
        help="待审计的提交信息草案文件路径",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="草案文件路径或直接传入的提交信息文本；省略时从标准输入读取",
    )
    args = parser.parse_args()

    if args.file_path:
        try:
            with open(args.file_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as exc:
            print(f"❌ 无法读取文件 {args.file_path}: {exc}", file=sys.stderr)
            return 1
    elif args.inputs:
        arg = args.inputs[0]
        if len(args.inputs) == 1 and os.path.isfile(arg):
            with open(arg, encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = " ".join(args.inputs)
    else:
        text = _read_stdin_utf8()

    found_errors = check_content(text)

    if found_errors:
        print("❌ 验证失败:")
        for err in found_errors:
            print(f"- {err}")
        return 1

    print("✅ 验证通过: 未发现路径泄露、隐私链接或格式问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
