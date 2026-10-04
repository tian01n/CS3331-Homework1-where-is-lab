"""独立、可缩放的 Protocol 阅读窗口，以及导入前的文字预览。"""

import tkinter as tk
from tkinter import font, ttk
from theme import APP_NAME, COLORS, style_text


class ProtocolReader(tk.Toplevel):
    def __init__(self, master, name, body, notes="", files=(), open_file=None, dirty=False):
        super().__init__(master)
        self.title(f"{APP_NAME} · Protocol 阅读 — {name or '未命名'}")
        self.geometry("1100x780")
        self.minsize(650, 450)
        self.resizable(True, True)
        self.configure(background=COLORS["page"])
        self.ui_font_family = getattr(master.winfo_toplevel(), "ui_font_family", "Microsoft YaHei UI")
        self.fullscreen = False
        self.files = list(files)
        self.open_file_callback = open_file
        self.reading_font = font.Font(self, family=self.ui_font_family, size=15)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(self, padding=(16, 12))
        toolbar.grid(row=0, column=0, sticky="ew")
        heading = ttk.Label(toolbar, text=name or "未命名 Protocol", font=(self.ui_font_family, 15, "bold"), wraplength=620)
        heading.pack(side="left", fill="x", expand=True)
        toolbar.bind("<Configure>", lambda event: heading.configure(wraplength=max(220, event.width - 340)))
        ttk.Button(toolbar, text="全屏 (F11)", command=self.toggle_fullscreen, style="Primary.TButton").pack(side="right", padx=4)
        ttk.Button(toolbar, text="字体 +", command=lambda: self.change_font(2)).pack(side="right", padx=4)
        ttk.Button(toolbar, text="字体 −", command=lambda: self.change_font(-2)).pack(side="right", padx=4)
        notice = "未保存的编辑内容预览；关闭阅读窗口不会保存。" if dirty else "已保存内容的阅读快照。"
        ttk.Label(self, text=notice + " 可拖动边缘放大或最大化；Esc 退出全屏。", style="Muted.TLabel", padding=(16, 0, 16, 8)).grid(
            row=1, column=0, sticky="ew"
        )
        self.notice = notice
        frame = ttk.Frame(self)
        frame.grid(row=2, column=0, sticky="nsew", padx=16)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.text = tk.Text(frame, wrap="word", font=self.reading_font, background=COLORS["surface"],
                            foreground=COLORS["text"], relief="flat", padx=32, pady=26,
                            spacing1=4, spacing3=6)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.insert("1.0", body or "（暂无正文。可打开原始文件查看。）")
        if notes:
            self.text.insert("end", "\n\n——备注——\n" + notes)
        self.text.configure(state="disabled")
        footer = ttk.Frame(self, padding=(16, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        if self.files:
            self.file_choice = ttk.Combobox(footer, state="readonly", width=24,
                                           values=[f"{i + 1}. {item['original_name']}" for i, item in enumerate(self.files)])
            self.file_choice.current(0)
            self.file_choice.grid(row=0, column=0, sticky="ew")
            ttk.Button(footer, text="打开原始文件", command=self.open_original).grid(row=0, column=1, padx=8)
        ttk.Button(footer, text="关闭阅读", command=self.destroy).grid(row=0, column=2, sticky="e")
        self.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.bind("<Escape>", lambda _event: self.exit_fullscreen())

    def change_font(self, delta):
        size = min(36, max(10, self.reading_font.cget("size") + delta))
        self.reading_font.configure(size=size)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.attributes("-fullscreen", self.fullscreen)

    def exit_fullscreen(self):
        self.fullscreen = False
        self.attributes("-fullscreen", False)

    def open_original(self):
        if self.open_file_callback is not None:
            self.open_file_callback(self.files[self.file_choice.current()])


class ImportPreview(tk.Toplevel):
    """提取结果由用户决定替换、追加、仅保留附件或取消。"""
    def __init__(self, master, result):
        super().__init__(master)
        self.title(f"{APP_NAME} · Protocol 文件导入预览")
        self.geometry("900x650")
        self.minsize(620, 420)
        self.configure(background=COLORS["page"])
        self.ui_font_family = getattr(master.winfo_toplevel(), "ui_font_family", "Microsoft YaHei UI")
        self.choice = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        metadata = result["file"]
        ttk.Label(self, text=metadata["original_name"], font=(self.ui_font_family, 13, "bold"), wraplength=800,
                  padding=12).grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=metadata["extraction_note"], wraplength=800, style="Muted.TLabel", padding=(12, 0, 12, 8)).grid(
            row=1, column=0, sticky="ew"
        )
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.preview_text = tk.Text(frame, wrap="word", font=("Microsoft YaHei", 12), padx=12, pady=12)
        style_text(self.preview_text, size=12)
        self.preview_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.preview_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.preview_text.configure(yscrollcommand=scroll.set)
        self.preview_text.insert("1.0", result["text"] or "没有可用文字。你仍可保留附件、打开原件，并手动填写正文。")
        self.preview_text.configure(state="disabled")
        buttons = ttk.Frame(self, padding=12)
        buttons.grid(row=3, column=0, sticky="ew")
        for label, choice in (("替换正文", "replace"), ("追加到正文", "append"),
                              ("仅保存附件", "attachment"), ("取消导入", None)):
            button = ttk.Button(buttons, text=label, command=lambda value=choice: self.finish(value),
                                style="Primary.TButton" if choice == "replace" else "TButton")
            button.pack(side="left", padx=5)
            if choice in ("replace", "append") and not result["text"].strip():
                button.state(["disabled"])
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", lambda: self.finish(None))

    def finish(self, choice):
        self.choice = choice
        self.destroy()

    @classmethod
    def ask(cls, master, result):
        dialog = cls(master, result)
        dialog.grab_set()
        master.wait_window(dialog)
        return dialog.choice
