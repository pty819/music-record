#!/usr/bin/env python3
"""07:00 补货 + 清 music 看板。

报告不在 origin/main，或 Camoufox JSON 晚到，就再跑出货管道。
无论是否补货，都会 complete/archive tenant=music 的残留任务。
无补货且无残留则 stdout 为空，no_agent cron 不投递。
"""
import os
import sys
from pathlib import Path

pipeline = Path(__file__).with_name("daily_pipeline.py")
os.execv(sys.executable, [sys.executable, str(pipeline), "--if-needed", *sys.argv[1:]])
