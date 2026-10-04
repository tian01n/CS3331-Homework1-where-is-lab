"""程序启动入口。运行命令：python main.py"""

from __future__ import annotations

import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from database import Database
from ui import LabInventoryApp


def main() -> None:
    """初始化本地数据库并启动主窗口。"""
    database_path = Path(__file__).resolve().parent / "lab_inventory.db"
    database = Database(database_path)
    try:
        database.initialize()
    except sqlite3.Error:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror(
            "启动失败", "无法创建或打开本地数据库，请检查项目目录是否可写。"
        )
        error_root.destroy()
        return

    app = LabInventoryApp(database)
    app.mainloop()


if __name__ == "__main__":
    main()

