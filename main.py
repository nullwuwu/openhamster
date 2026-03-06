#!/usr/bin/env python3
"""
Quant Trader 主入口

支持两种运行模式:
- --run-now: 立即执行一次
- --daemon: 常驻后台定时触发
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from quant_trader.scheduler import main

if __name__ == "__main__":
    main()
