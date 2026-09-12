#!/usr/bin/env python3
"""07:00 补货。报告不在 origin/main，或 Camoufox JSON 晚到，就再跑出货管道。

不创建 swarm。无事可做则 stdout 为空，no_agent cron 不投递。
"""
import os
import sys
from pathlib import Path

pipeline = Path(__file__).with_name("daily_pipeline.py")
os.execv(sys.executable, [sys.executable, str(pipeline), "--if-needed", *sys.argv[1:]])
