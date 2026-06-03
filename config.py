"""读取 .env 配置（无第三方依赖）。

任何脚本只要 `import config` 就会自动加载 .env 中的环境变量。
"""
import os
import sys

# Windows 控制台默认 GBK 编码，打印 emoji/部分中文会崩溃；强制 UTF-8 输出。
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def load_env():
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

if not os.getenv("DASHSCOPE_API_KEY"):
    raise SystemExit(
        "请在 .env 里填 DASHSCOPE_API_KEY\n"
        "提示：复制 .env.example 为 .env，再填入你的 key。"
    )
