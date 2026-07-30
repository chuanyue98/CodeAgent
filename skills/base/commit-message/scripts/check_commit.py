import os
import re
import sys

# The ✅/❌ result banners cannot be encoded by a non-UTF-8 console (cp936 on a
# Chinese Windows install, for one), so every run died on a UnicodeEncodeError
# at the very last line -- the check's verdict never reached the caller, pass
# or fail. Mirrors core/console.py; skills run standalone from an arbitrary
# cwd, so they cannot import it.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def check_content(content):
    """
    检查提交信息草案是否包含隐私泄露或格式问题。
    """
    errors = []

    # 规则 1: 禁止本地绝对路径 (如 D:\ 或 C:\)
    absolute_path_pattern = r"[a-zA-Z]:[\\/][^ \n]*"
    if re.search(absolute_path_pattern, content):
        paths = re.findall(absolute_path_pattern, content)
        errors.append(f"发现本地绝对路径: {', '.join(paths)}")

    # 规则 2: 禁止 IDE 注入的 cci:// 引用
    cci_pattern = r"cci://[^\s)]*"
    if re.search(cci_pattern, content):
        errors.append("发现 IDE 注入的 cci:// 引用")

    # 规则 3: 禁止 Markdown 链接格式 [...](...)，防止路径关联
    markdown_link_pattern = r"\[.*\]\(.*\)"
    if re.search(markdown_link_pattern, content):
        errors.append("发现 Markdown 链接格式，请保持纯文本")

    return errors


if __name__ == "__main__":
    # 解析输入内容
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # 如果是文件路径则读取文件，否则视为直接传入的文本
        if os.path.isfile(arg):
            with open(arg, encoding="utf-8") as f:
                text = f.read()
        else:
            text = " ".join(sys.argv[1:])
    else:
        # 从标准输入读取
        text = sys.stdin.read()

    found_errors = check_content(text)

    if found_errors:
        print("❌ 验证失败:")
        for err in found_errors:
            print(f"- {err}")
        sys.exit(1)
    else:
        print("✅ 验证通过: 未发现路径泄露、隐私链接或格式问题。")
        sys.exit(0)
