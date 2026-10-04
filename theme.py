"""Where Is...? 的共享样式；只改变显示，不改变数据或业务行为。"""

from __future__ import annotations

import tkinter as tk
from tkinter import font, ttk


APP_NAME = "Where Is...?"
COLORS = {
    "page": "#F3F5FA", "surface": "#FFFFFF", "text": "#213149",
    "muted": "#718096", "border": "#DFE6F0", "accent": "#285DCD",
    "accent_hover": "#194BAF", "tint": "#EDF3FF", "stripe": "#F7F9FD",
    "danger": "#B83D48", "danger_tint": "#FFF0F1", "warning": "#966017",
}


def set_app_icon(root: tk.Tk) -> None:
    """代码绘制的小定位图标，不引入图片文件或额外依赖。"""
    icon = tk.PhotoImage(master=root, width=32, height=32)
    icon.put(COLORS["accent"], to=(0, 0, 32, 32))
    for y in range(5, 29):
        for x in range(6, 27):
            distance = (x - 16) ** 2 + (y - 13) ** 2
            head = distance <= 9 ** 2
            tail = 14 <= y <= 28 and abs(x - 16) <= (28 - y) * 0.65
            if (head or tail) and distance > 3 ** 2:
                icon.put("white", to=(x, y))
    root.brand_icon = icon
    root.iconphoto(True, icon)


def setup_theme(root: tk.Tk) -> None:
    families = set(font.families(root))
    family = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "TkDefaultFont"
    root.ui_font_family = family
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        font.Font(root=root, name=name, exists=True).configure(family=family, size=10)
    root.configure(background=COLORS["page"])
    set_app_icon(root)
    root.option_add("*TCombobox*Listbox.font", (family, 10))
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(family, 10), foreground=COLORS["text"],
                    background=COLORS["surface"], bordercolor=COLORS["border"],
                    lightcolor=COLORS["border"], darkcolor=COLORS["border"])
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("Page.TFrame", background=COLORS["page"])
    style.configure("TLabel", background=COLORS["surface"])
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
    style.configure("Section.TLabel", font=(family, 12, "bold"))
    style.configure("Badge.TLabel", foreground=COLORS["accent"],
                    background=COLORS["tint"], padding=(10, 5), font=(family, 9))
    style.configure("Footer.TLabel", background=COLORS["page"],
                    foreground=COLORS["muted"], font=(family, 9))
    style.configure("Empty.TLabel", foreground=COLORS["muted"],
                    background=COLORS["surface"], padding=16, font=(family, 10))
    style.configure("TLabelframe", background=COLORS["surface"],
                    borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=COLORS["surface"],
                    foreground=COLORS["text"], font=(family, 10, "bold"))
    style.configure("TButton", padding=(12, 7), relief="flat", borderwidth=1,
                    background=COLORS["surface"], foreground=COLORS["text"],
                    focusthickness=1, focuscolor=COLORS["accent"])
    style.map("TButton", background=[("active", COLORS["tint"])],
              foreground=[("disabled", "#9BA7B7")])
    style.configure("Primary.TButton", background=COLORS["accent"],
                    foreground="white", font=(family, 10, "bold"), borderwidth=0)
    style.map("Primary.TButton", background=[("disabled", "#B3C6EE"),
              ("pressed", COLORS["accent_hover"]), ("active", COLORS["accent_hover"])],
              foreground=[("disabled", "white"), ("!disabled", "white")])
    style.configure("Danger.TButton", foreground=COLORS["danger"])
    style.map("Danger.TButton", background=[("active", COLORS["danger_tint"])])
    style.configure("TEntry", padding=(9, 7), fieldbackground=COLORS["surface"],
                    borderwidth=1, insertcolor=COLORS["text"])
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
    style.configure("TCombobox", padding=(9, 6), fieldbackground=COLORS["surface"],
                    arrowcolor=COLORS["muted"], borderwidth=1)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["surface"])],
              foreground=[("readonly", COLORS["text"])],
              bordercolor=[("focus", COLORS["accent"])],
              selectbackground=[("readonly", COLORS["surface"])],
              selectforeground=[("readonly", COLORS["text"])])
    style.configure("Treeview", background=COLORS["surface"],
                    fieldbackground=COLORS["surface"], rowheight=32, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["stripe"],
                    foreground=COLORS["muted"], font=(family, 9, "bold"),
                    padding=(9, 9), relief="flat", borderwidth=0)
    style.map("Treeview", background=[("selected", COLORS["tint"])],
              foreground=[("selected", COLORS["accent"])])
    style.map("Treeview.Heading", background=[("active", COLORS["tint"])])
    style.configure("TNotebook", background=COLORS["surface"], borderwidth=0,
                    tabmargins=(0, 0, 0, 4))
    style.configure("TNotebook.Tab", padding=(12, 5), background=COLORS["stripe"], font=(family, 10))
    style.map("TNotebook.Tab", background=[("selected", COLORS["tint"])],
              foreground=[("selected", COLORS["accent"])],
              # 覆盖 clam 主题内置的 selected 小内边距，避免选中后反而缩小。
              padding=[("selected", (15, 9, 15, 8)), ("!selected", (12, 5, 12, 5))],
              font=[("selected", (family, 11, "bold")), ("!selected", (family, 10))])
    style.configure("Main.TNotebook", background=COLORS["page"], tabmargins=(0, 0, 0, 4))
    style.configure("Main.TNotebook.Tab", padding=(18, 6), font=(family, 10, "bold"))
    style.map("Main.TNotebook.Tab", background=[("selected", COLORS["accent"]),
              ("!selected", COLORS["surface"])],
              foreground=[("selected", "white"), ("!selected", COLORS["muted"])],
              padding=[("selected", (20, 10, 20, 8)), ("!selected", (18, 6, 18, 6))],
              font=[("selected", (family, 11, "bold")), ("!selected", (family, 10, "bold"))])
    style.configure("TPanedwindow", background=COLORS["page"])
    style.configure("Sash", sashthickness=10, background=COLORS["page"])
    style.configure("Vertical.TScrollbar", background=COLORS["border"],
                    troughcolor=COLORS["surface"], borderwidth=0, arrowsize=12)
    style.configure("Horizontal.TScrollbar", background=COLORS["border"],
                    troughcolor=COLORS["surface"], borderwidth=0, arrowsize=12)


def style_text(widget: tk.Text, *, size: int = 10) -> None:
    family = getattr(widget.winfo_toplevel(), "ui_font_family", "Microsoft YaHei UI")
    widget.configure(font=(family, size), background=COLORS["surface"],
                     foreground=COLORS["text"], insertbackground=COLORS["accent"],
                     selectbackground=COLORS["tint"], selectforeground=COLORS["accent"],
                     relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=COLORS["border"], highlightcolor=COLORS["accent"],
                     padx=10, pady=8, spacing3=4)


def stripe_rows(table: ttk.Treeview) -> None:
    table.tag_configure("stripe_even", background=COLORS["surface"])
    table.tag_configure("stripe_odd", background=COLORS["stripe"])
    index = 0
    def visit(parent=""):
        nonlocal index
        for iid in table.get_children(parent):
            tags = [tag for tag in table.item(iid, "tags") if not tag.startswith("stripe_")]
            table.item(iid, tags=(*tags, "stripe_odd" if index % 2 else "stripe_even"))
            index += 1
            visit(iid)
    visit()


def show_empty_state(table: ttk.Treeview, message: str) -> None:
    if not hasattr(table, "empty_label"):
        table.empty_label = ttk.Label(table, style="Empty.TLabel", justify="center",
                                      anchor="center", wraplength=270)
    table.empty_label.configure(text=message)
    if table.get_children():
        table.empty_label.place_forget()
    else:
        table.empty_label.place(relx=0.5, rely=0.58, anchor="center", relwidth=0.88)


def initial_sash(panes: ttk.Panedwindow, proportion: float) -> None:
    """第一次有可用尺寸时分配空间，之后保留用户自己拖动的分隔线。"""
    initialized = False
    def place(_event=None):
        nonlocal initialized
        if initialized:
            return
        extent = panes.winfo_width() if str(panes.cget("orient")) == "horizontal" else panes.winfo_height()
        if extent > 100:
            panes.sashpos(0, int(extent * proportion))
            initialized = True
    panes.bind("<Configure>", place, add="+")


class ScrollableForm(ttk.Frame):
    """独立滚动的表单或关联区域，窗口变小时仍能找到完整内容。"""

    def __init__(self, master, *, width=350, height=380, padding=0):
        super().__init__(master, padding=padding)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=COLORS["surface"], highlightthickness=0,
                                borderwidth=0, width=width, height=height)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.content = ttk.Frame(self.canvas, padding=(0, 0, 10, 0))
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self._wheel_enabled = False
        self._scroll_nested = False
        self._wheel_tag = f"WhereIsScroll{id(self)}"
        self.canvas.bind("<Configure>", self._sync_content)
        self.content.bind("<Configure>", self._sync_content)

    def _sync_content(self, _event=None):
        width = max(1, self.canvas.winfo_width())
        height = max(self.content.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.itemconfigure(self.window_id, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if self._wheel_enabled:
            self._attach_wheel_tags()

    def scroll_vertical(self, units):
        """返回是否确实滚动，供边界处的嵌套列表继续处理滚轮。"""
        before = self.canvas.yview()
        region = self.canvas.tk.splitlist(self.canvas.cget("scrollregion"))
        if len(region) != 4:
            return False
        height = max(1.0, float(region[3]) - float(region[1]))
        # 用像素距离而非固定 yscrollincrement，防止很小的视口在末端滚过内容。
        self.canvas.yview_moveto(before[0] + units * 24 / height)
        return self.canvas.yview() != before

    def _on_mousewheel(self, event):
        if not event.delta or event.state & 0x0001:  # Shift 留给列表横向滚动。
            return None
        if self.content.winfo_reqheight() <= self.canvas.winfo_height():
            return None
        units = max(1, abs(event.delta) // 120)
        if self.scroll_vertical(-units if event.delta > 0 else units):
            return "break"
        return None

    def _attach_wheel_tags(self):
        def attach(widget):
            # 普通表单不抢走文本/列表滚轮；编辑页被裁切时可先滚动整个面板。
            nested = isinstance(widget, (tk.Text, ttk.Treeview))
            if not isinstance(widget, ttk.Combobox) and (self._scroll_nested or not nested):
                tags = widget.bindtags()
                if self._wheel_tag not in tags:
                    widget.bindtags((self._wheel_tag, *tags))
            for child in widget.winfo_children():
                attach(child)
        attach(self)

    def bind_wheel(self, *, scroll_nested=False):
        self._scroll_nested = scroll_nested
        if not self._wheel_enabled:
            self.bind_class(self._wheel_tag, "<MouseWheel>", self._on_mousewheel)
            self._wheel_enabled = True
        self._attach_wheel_tags()

    def destroy(self):
        if self._wheel_enabled:
            self.unbind_class(self._wheel_tag, "<MouseWheel>")
        super().destroy()
