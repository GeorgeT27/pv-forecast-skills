#!/usr/bin/env python3
"""金标准闸对象：直接调用生产脚本 scripts/improve_verdict.py 的 main()——同一份代码，不复制逻辑。"""
import os
import sys

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(ENGINE_DIR, "scripts"))

import improve_verdict  # noqa: E402

if __name__ == "__main__":
    improve_verdict.main()
