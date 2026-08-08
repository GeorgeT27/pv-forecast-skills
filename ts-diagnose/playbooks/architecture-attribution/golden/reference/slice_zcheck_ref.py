#!/usr/bin/env python3
"""金标准闸对象：直接调用生产脚本 scripts/slice_zcheck.py 的 main()——同一份代码，
不复制逻辑、不会产生副本漂移。gen_gate 只需要一个可执行脚本路径，这里用 sys.path
接到真实 scripts/ 目录后转发。"""
import os
import sys

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(ENGINE_DIR, "scripts"))

import slice_zcheck  # noqa: E402

if __name__ == "__main__":
    slice_zcheck.main()
