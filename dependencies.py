"""可选文件解析依赖：兼容常规安装和项目内 .vendor 安装。"""

import importlib
import sys
from pathlib import Path


def optional_module(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        vendor = Path(__file__).resolve().parent / ".vendor"
        if vendor.is_dir() and str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        return importlib.import_module(name)
