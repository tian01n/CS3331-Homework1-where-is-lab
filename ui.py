"""Tkinter 图形界面。"""

from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from database import Database
from protocol_ui import ProtocolPanel
from services import AppError, CATEGORIES, ItemService, LocationService, ProtocolService
from theme import APP_NAME, COLORS, ScrollableForm, initial_sash, setup_theme, show_empty_state, stripe_rows, style_text


ALL_CATEGORIES = "全部类别"
NO_PARENT = "（无上级位置）"


class LabInventoryApp(tk.Tk):
    """Where Is...? 实验室物品与 Protocol 主窗口。"""

    def __init__(self, database: Database) -> None:
        super().__init__()
        self.title(APP_NAME)
        setup_theme(self)
        width = min(1320, max(900, self.winfo_screenwidth() - 100))
        height = min(860, max(650, self.winfo_screenheight() - 100))
        self.geometry(f"{width}x{height}")
        self.minsize(min(1040, width), min(720, height))
        self.overview_var = tk.StringVar(value="你的实验室，一目了然")
        self.footer_var = tk.StringVar(value="本地数据 · 编辑后请点击保存")
        self.item_mode_var = tk.StringVar(value="新建物品")
        self.item_count_var = tk.StringVar()
        self.location_count_var = tk.StringVar()

        self.location_service = LocationService(database)
        self.item_service = ItemService(database)
        self.protocol_service = ProtocolService(database)
        self._refreshing_items = False
        self.selected_item_id: int | None = None
        self.selected_location_id: int | None = None
        self.item_location_by_label: dict[str, int] = {}
        self.item_location_label_by_id: dict[int, str] = {}
        self.parent_by_label: dict[str, int | None] = {NO_PARENT: None}
        self.parent_label_by_id: dict[int | None, str] = {None: NO_PARENT}

        self._build_ui()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.close_requested)

    def close_requested(self) -> None:
        """窗口关闭前保护 Protocol 正文与待保存关联。"""
        if self.protocol_panel.confirm_discard_changes():
            self.destroy()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(16, 8))
        self.header = header
        header.pack(fill="x")
        logo = tk.Canvas(header, width=32, height=32, background=COLORS["accent"],
                         highlightthickness=0)
        self.brand_logo = logo
        logo.pack(side="left", padx=(0, 10))
        logo.create_polygon(9, 18, 16, 28, 23, 18, fill="white", outline="white")
        logo.create_oval(7, 4, 25, 22, fill="white", outline="white")
        logo.create_oval(13, 10, 19, 16, fill=COLORS["accent"], outline=COLORS["accent"])
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="本地 · 离线", style="Badge.TLabel").pack(side="right", padx=(12, 0))
        ttk.Label(header, textvariable=self.overview_var, style="Muted.TLabel").pack(side="right")
        footer = ttk.Frame(self, style="Page.TFrame", padding=(16, 4))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, textvariable=self.footer_var, style="Footer.TLabel").pack(side="left")
        ttk.Label(footer, text="Where Is...?  /  LAB WORKSPACE", style="Footer.TLabel").pack(side="right")
        notebook = ttk.Notebook(self, style="Main.TNotebook")
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        self.item_tab = ttk.Frame(notebook, style="Page.TFrame")
        self.location_tab = ttk.Frame(notebook, style="Page.TFrame")
        notebook.add(self.item_tab, text="物品管理")
        notebook.add(self.location_tab, text="位置管理")

        self._build_item_tab()
        self._build_location_tab()
        self.protocol_panel = ProtocolPanel(
            notebook, self.protocol_service, self.item_service,
            self._after_protocol_saved, self._display_error,
        )
        notebook.add(self.protocol_panel, text="Protocol 管理")

    def _after_protocol_saved(self) -> None:
        self.refresh_item_protocols()
        self._update_overview()

    def _update_overview(self) -> None:
        items = len(self.item_service.search_items())
        locations = len(self.location_service.list_locations())
        protocols = len(self.protocol_service.search_protocols())
        self.overview_var.set(f"{items} 件物品   ·   {locations} 个位置   ·   {protocols} 份 Protocol")
        if not locations:
            self.footer_var.set("初次使用：先在“位置管理”建立位置，再添加物品。")
        else:
            self.footer_var.set("本地数据 · 编辑后请点击保存 · 可拖动分隔线调整空间")

    # ---------- 物品管理界面 ----------

    def _build_item_tab(self) -> None:
        tab = self.item_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(tab, padding=10)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        search_frame.columnconfigure(1, weight=1)

        self.search_var = tk.StringVar()
        self.filter_category_var = tk.StringVar(value=ALL_CATEGORIES)
        ttk.Label(search_frame, text="查找物品", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(4, 12))
        search_entry.bind("<Return>", lambda _event: self.refresh_items())
        ttk.Label(search_frame, text="类别：").grid(row=0, column=2, sticky="w")
        filter_combo = ttk.Combobox(
            search_frame,
            textvariable=self.filter_category_var,
            values=(ALL_CATEGORIES, *CATEGORIES),
            state="readonly",
            width=12,
        )
        filter_combo.grid(row=0, column=3, padx=(4, 8))
        filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_items())
        ttk.Button(search_frame, text="搜索", command=self.refresh_items, style="Primary.TButton").grid(
            row=0, column=4, padx=4
        )
        ttk.Button(search_frame, text="显示全部", command=self.show_all_items).grid(
            row=0, column=5, padx=(4, 0)
        )

        self.item_panes = ttk.Panedwindow(tab, orient="horizontal")
        self.item_panes.grid(row=1, column=0, sticky="nsew")
        listing = ttk.Frame(self.item_panes, padding=16)
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(1, weight=1)
        details = ttk.Frame(self.item_panes, padding=16)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(1, weight=1)
        self.item_panes.add(listing, weight=3)
        self.item_panes.add(details, weight=1)
        initial_sash(self.item_panes, 0.67)
        list_header = ttk.Frame(listing)
        list_header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(list_header, text="物品清单", style="Section.TLabel").pack(side="left")
        ttk.Label(list_header, textvariable=self.item_count_var, style="Muted.TLabel").pack(side="left", padx=12)
        ttk.Button(list_header, text="＋ 新建物品", command=self.clear_item_form).pack(side="right")
        ttk.Label(details, textvariable=self.item_mode_var, style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12))
        self.item_scroll_form = ScrollableForm(details)
        self.item_scroll_form.grid(row=1, column=0, sticky="nsew")
        form = self.item_scroll_form.content
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        self.item_primary_var = tk.StringVar()
        self.item_chinese_var = tk.StringVar()
        self.item_english_var = tk.StringVar()
        self.item_category_var = tk.StringVar(value=CATEGORIES[0])
        self.item_location_var = tk.StringVar()

        ttk.Label(form, text="主要名称 *").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Entry(form, textvariable=self.item_primary_var).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12)
        )
        ttk.Label(form, text="中文名").grid(row=2, column=0, sticky="w", pady=(0, 5))
        ttk.Entry(form, textvariable=self.item_chinese_var).grid(
            row=3, column=0, sticky="ew", padx=(0, 8), pady=(0, 12)
        )
        ttk.Label(form, text="英文名").grid(row=2, column=1, sticky="w", pady=(0, 5))
        ttk.Entry(form, textvariable=self.item_english_var).grid(
            row=3, column=1, sticky="ew", pady=(0, 12)
        )
        ttk.Label(form, text="类别 *").grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Combobox(
            form,
            textvariable=self.item_category_var,
            values=CATEGORIES,
            state="readonly",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        ttk.Label(form, text="所在位置 *").grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.item_location_combo = ttk.Combobox(
            form, textvariable=self.item_location_var, state="readonly"
        )
        self.item_location_combo.grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(0, 12)
        )

        ttk.Label(form, text="别名 · 用逗号或换行分隔", style="Muted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.item_alias_text = tk.Text(form, height=3, width=20, wrap="word")
        style_text(self.item_alias_text)
        self.item_alias_text.grid(
            row=9, column=0, columnspan=2, sticky="ew", pady=(0, 12)
        )
        ttk.Label(form, text="备注").grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 5))
        self.item_notes_text = tk.Text(form, height=3, width=20, wrap="word")
        style_text(self.item_notes_text)
        self.item_notes_text.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.item_scroll_form.bind_wheel()

        button_frame = ttk.Frame(details)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        ttk.Button(button_frame, text="保存新物品", command=self.add_item, style="Primary.TButton").grid(
            row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(button_frame, text="保存修改", command=self.update_item).grid(
            row=0, column=1, sticky="ew")
        ttk.Button(button_frame, text="删除物品", command=self.delete_item, style="Danger.TButton").grid(
            row=1, column=0, sticky="ew", padx=(0, 6), pady=(8, 0))
        ttk.Button(button_frame, text="清空表单", command=self.clear_item_form).grid(
            row=1, column=1, sticky="ew", pady=(8, 0))

        table_frame = ttk.Frame(listing)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = (
            "id",
            "primary_name",
            "chinese_name",
            "english_name",
            "aliases",
            "category",
            "location_path",
            "notes",
        )
        self.item_table = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.item_table.configure(displaycolumns=("id", "primary_name", "category", "location_path", "aliases"))
        headings = {
            "id": "编号",
            "primary_name": "主要名称",
            "chinese_name": "中文名",
            "english_name": "英文名",
            "aliases": "别名",
            "category": "类别",
            "location_path": "完整位置路径",
            "notes": "备注",
        }
        widths = {
            "id": 55,
            "primary_name": 190,
            "chinese_name": 110,
            "english_name": 130,
            "aliases": 140,
            "category": 70,
            "location_path": 225,
            "notes": 160,
        }
        for column in columns:
            self.item_table.heading(column, text=headings[column])
            self.item_table.column(column, width=widths[column], minwidth=50)
        self.item_table.column("id", stretch=False, anchor="center")
        self.item_table.column("category", stretch=False, anchor="center")
        self.item_table.grid(row=0, column=0, sticky="nsew")
        self.item_table.bind("<<TreeviewSelect>>", self.on_item_selected)

        vertical_scroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.item_table.yview
        )
        horizontal_scroll = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.item_table.xview
        )
        self.item_table.configure(
            yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set
        )
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll.grid(row=1, column=0, sticky="ew")

        reverse_frame = ttk.LabelFrame(listing, text="使用所选物品的 Protocol", padding=10)
        reverse_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        reverse_frame.columnconfigure(0, weight=1)
        self.item_protocol_table = ttk.Treeview(
            reverse_frame, columns=("id", "name"), show="headings",
            height=2, selectmode="browse",
        )
        self.item_protocol_table.heading("id", text="编号")
        self.item_protocol_table.heading("name", text="Protocol 名称")
        self.item_protocol_table.column("id", width=60, stretch=False)
        self.item_protocol_table.column("name", width=350)
        self.item_protocol_table.grid(row=0, column=0, sticky="ew")
        reverse_scroll = ttk.Scrollbar(
            reverse_frame, orient="vertical", command=self.item_protocol_table.yview
        )
        self.item_protocol_table.configure(yscrollcommand=reverse_scroll.set)
        reverse_scroll.grid(row=0, column=1, sticky="ns")
        ttk.Button(
            reverse_frame, text="打开所选 Protocol", command=self.open_item_protocol
        ).grid(row=0, column=2, padx=(8, 0))
        self.item_protocol_table.bind(
            "<Double-1>", lambda _event: self.open_item_protocol()
        )

    # ---------- 位置管理界面 ----------

    def _build_location_tab(self) -> None:
        tab = self.location_tab
        tab.columnconfigure(0, weight=3)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(0, weight=1)

        tree_frame = ttk.LabelFrame(tab, text="位置层级", padding=16)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(1, weight=1)
        ttk.Label(tree_frame, textvariable=self.location_count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12))

        self.location_tree = ttk.Treeview(
            tree_frame, columns=("id", "notes"), show="tree headings"
        )
        self.location_tree.heading("#0", text="位置名称")
        self.location_tree.heading("id", text="编号")
        self.location_tree.heading("notes", text="备注")
        self.location_tree.column("#0", width=250, minwidth=140)
        self.location_tree.column("id", width=60, stretch=False, anchor="center")
        self.location_tree.column("notes", width=220, minwidth=100)
        self.location_tree.grid(row=1, column=0, sticky="nsew")
        self.location_tree.bind("<<TreeviewSelect>>", self.on_location_selected)
        location_scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.location_tree.yview
        )
        self.location_tree.configure(yscrollcommand=location_scroll.set)
        location_scroll.grid(row=1, column=1, sticky="ns")

        form = ttk.LabelFrame(tab, text="位置详情", padding=16)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(4, weight=1)

        self.location_name_var = tk.StringVar()
        self.location_parent_var = tk.StringVar(value=NO_PARENT)
        self.location_path_var = tk.StringVar(value="尚未选择位置")

        ttk.Label(form, text="位置名称*：").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.location_name_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 0), pady=4
        )
        ttk.Label(form, text="上级位置：").grid(row=1, column=0, sticky="w", pady=4)
        self.location_parent_combo = ttk.Combobox(
            form, textvariable=self.location_parent_var, state="readonly"
        )
        self.location_parent_combo.grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=4
        )
        ttk.Label(form, text="完整路径：").grid(row=2, column=0, sticky="nw", pady=4)
        ttk.Label(
            form,
            textvariable=self.location_path_var,
            wraplength=390,
            foreground=COLORS["accent"],
        ).grid(row=2, column=1, sticky="w", padx=(6, 0), pady=4)
        ttk.Label(form, text="备注：").grid(row=3, column=0, sticky="nw", pady=4)
        self.location_notes_text = tk.Text(form, height=8, width=28, wrap="word")
        style_text(self.location_notes_text)
        self.location_notes_text.grid(
            row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8)
        )

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        for index, (label, command, style) in enumerate((
            ("保存新位置", self.add_location, "Primary.TButton"),
            ("保存修改", self.update_location, "TButton"),
            ("删除位置", self.delete_location, "Danger.TButton"),
            ("清空表单", self.clear_location_form, "TButton"),
        )):
            ttk.Button(buttons, text=label, command=command, style=style).grid(
                row=index // 2, column=index % 2, sticky="ew", padx=3, pady=4)

    # ---------- 公共刷新和错误提示 ----------

    @staticmethod
    def _get_text(widget: tk.Text) -> str:
        return widget.get("1.0", "end-1c")

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    @staticmethod
    def _display_error(action: str, error: Exception) -> None:
        if isinstance(error, AppError):
            message = str(error)
        elif isinstance(error, sqlite3.Error):
            message = "数据库操作失败，请确认数据库文件可访问后重试。"
        else:
            message = "操作未能完成，请检查输入后重试。"
        messagebox.showerror(f"{action}失败", message)

    def refresh_all(self) -> None:
        try:
            locations = self.location_service.list_locations()
            self._refresh_location_tree(locations)
            self._refresh_location_choices(locations)
            self.refresh_items()
            self.protocol_panel.refresh_item_views()
            self._update_overview()
        except Exception as error:
            self._display_error("刷新数据", error)

    def _refresh_location_choices(self, locations: list[dict]) -> None:
        # 先从旧映射取得编号，再建立新显示文字，改名或移动后选择仍有效。
        selected_item_location = self.item_location_by_label.get(self.item_location_var.get())
        selected_parent = self.parent_by_label.get(self.location_parent_var.get())
        self.item_location_by_label.clear()
        self.item_location_label_by_id.clear()
        self.parent_by_label = {NO_PARENT: None}
        self.parent_label_by_id = {None: NO_PARENT}
        labels: list[str] = []
        for location in locations:
            label = f"{location['full_path']}  [编号：{location['id']}]"
            labels.append(label)
            self.item_location_by_label[label] = location["id"]
            self.item_location_label_by_id[location["id"]] = label
            self.parent_by_label[label] = location["id"]
            self.parent_label_by_id[location["id"]] = label
        self.item_location_combo.configure(values=labels)
        self.location_parent_combo.configure(values=(NO_PARENT, *labels))

        self.item_location_var.set(
            self.item_location_label_by_id.get(selected_item_location, "")
        )
        self.location_parent_var.set(
            self.parent_label_by_id.get(selected_parent, NO_PARENT)
        )

    def _refresh_location_tree(self, locations: list[dict]) -> None:
        for item in self.location_tree.get_children():
            self.location_tree.delete(item)
        children: dict[int | None, list[dict]] = {}
        for location in locations:
            children.setdefault(location["parent_id"], []).append(location)

        def insert_children(parent_id: int | None, parent_iid: str) -> None:
            for location in children.get(parent_id, []):
                iid = f"location-{location['id']}"
                self.location_tree.insert(
                    parent_iid,
                    "end",
                    iid=iid,
                    text=location["name"],
                    values=(location["id"], location["notes"]),
                    open=True,
                )
                insert_children(location["id"], iid)

        insert_children(None, "")
        stripe_rows(self.location_tree)
        self.location_count_var.set(f"{len(locations)} 个位置 · 单击查看详情与完整路径")
        show_empty_state(self.location_tree, "还没有位置\n先在右侧建立“实验室”，再添加冰箱、层架等子位置。")

    # ---------- 物品操作 ----------

    def _item_form_values(self) -> dict:
        location_id = self.item_location_by_label.get(self.item_location_var.get())
        return {
            "primary_name": self.item_primary_var.get(),
            "chinese_name": self.item_chinese_var.get(),
            "english_name": self.item_english_var.get(),
            "aliases": self._get_text(self.item_alias_text),
            "category": self.item_category_var.get(),
            "notes": self._get_text(self.item_notes_text),
            "location_id": location_id,
        }

    def refresh_items(self) -> None:
        try:
            category = self.filter_category_var.get()
            selected_category = None if category == ALL_CATEGORIES else category
            rows = self.item_service.search_items(
                self.search_var.get(), selected_category
            )
            selected_id = self.selected_item_id
            self._refreshing_items = True
            for item in self.item_table.get_children():
                self.item_table.delete(item)
            for row in rows:
                self.item_table.insert(
                    "",
                    "end",
                    iid=f"item-{row['id']}",
                    values=(
                        row["id"],
                        row["primary_name"],
                        row["chinese_name"],
                        row["english_name"],
                        row["aliases"],
                        row["category"],
                        row["location_path"],
                        row["notes"].replace("\n", " "),
                    ),
                )
            stripe_rows(self.item_table)
            self.item_count_var.set(f"当前显示 {len(rows)} 件")
            filtered = bool(self.search_var.get().strip()) or selected_category is not None
            show_empty_state(self.item_table, "没有匹配的物品\n试试其他名称、别名，或点击“显示全部”。" if filtered else
                             "还没有物品\n先建立位置，再在右侧录入你的第一件物品。")
            if selected_id is not None:
                if any(row["id"] == selected_id for row in rows):
                    self.item_table.selection_set(f"item-{selected_id}")
                else:
                    self.clear_item_form()
            self.refresh_item_protocols()
            self._update_overview()
        except Exception as error:
            self._display_error("搜索物品", error)
        finally:
            self._refreshing_items = False

    def show_all_items(self) -> None:
        self.search_var.set("")
        self.filter_category_var.set(ALL_CATEGORIES)
        self.refresh_items()

    def add_item(self) -> None:
        try:
            self.item_service.create_item(**self._item_form_values())
            self.clear_item_form()
            self.refresh_items()
            self.protocol_panel.refresh_item_views()
            messagebox.showinfo("添加成功", "物品已保存。")
        except Exception as error:
            self._display_error("添加物品", error)

    def update_item(self) -> None:
        if not self._has_item_selection():
            messagebox.showwarning("未选择物品", "请先在表格中选择要修改的物品。")
            return
        try:
            self.item_service.update_item(
                self.selected_item_id, **self._item_form_values()
            )
            self.clear_item_form()
            self.refresh_items()
            self.protocol_panel.refresh_item_views()
            messagebox.showinfo("修改成功", "物品信息已更新。")
        except Exception as error:
            self._display_error("修改物品", error)

    def delete_item(self) -> None:
        if not self._has_item_selection():
            messagebox.showwarning("未选择物品", "请先在表格中选择要删除的物品。")
            return
        if not messagebox.askyesno("确认删除", "确定要删除所选物品吗？"):
            return
        try:
            self.item_service.delete_item(self.selected_item_id)
            self.clear_item_form()
            self.refresh_items()
            self.protocol_panel.refresh_item_views()
            messagebox.showinfo("删除成功", "物品已删除。")
        except Exception as error:
            self._display_error("删除物品", error)

    def on_item_selected(self, _event: tk.Event) -> None:
        if self._refreshing_items:
            return
        selection = self.item_table.selection()
        if not selection:
            if self.selected_item_id is not None:
                self.clear_item_form()
            return
        values = self.item_table.item(selection[0], "values")
        if not values:
            return
        if int(values[0]) == self.selected_item_id:
            return
        try:
            item = self.item_service.get_item(int(values[0]))
            self.selected_item_id = item["id"]
            self.item_mode_var.set(f"物品详情 · #{item['id']}")
            self.item_primary_var.set(item["primary_name"])
            self.item_chinese_var.set(item["chinese_name"])
            self.item_english_var.set(item["english_name"])
            self.item_category_var.set(item["category"])
            self.item_location_var.set(
                self.item_location_label_by_id.get(item["location_id"], "")
            )
            self._set_text(self.item_alias_text, "\n".join(item["aliases"]))
            self._set_text(self.item_notes_text, item["notes"])
            self.refresh_item_protocols()
        except Exception as error:
            self._display_error("读取物品", error)

    def clear_item_form(self) -> None:
        self.selected_item_id = None
        self.item_mode_var.set("新建物品")
        self.item_primary_var.set("")
        self.item_chinese_var.set("")
        self.item_english_var.set("")
        self.item_category_var.set(CATEGORIES[0])
        self.item_location_var.set("")
        self._set_text(self.item_alias_text, "")
        self._set_text(self.item_notes_text, "")
        for iid in self.item_table.selection():
            self.item_table.selection_remove(iid)
        self.refresh_item_protocols()

    def _has_item_selection(self) -> bool:
        """修改和删除同时检查实际表格选择，防止操作隐藏的旧编号。"""
        return (
            self.selected_item_id is not None
            and f"item-{self.selected_item_id}" in self.item_table.selection()
        )

    def refresh_item_protocols(self) -> None:
        try:
            for iid in self.item_protocol_table.get_children():
                self.item_protocol_table.delete(iid)
            if self.selected_item_id is None:
                show_empty_state(self.item_protocol_table, "选中物品后，可查看关联的 Protocol。")
                return
            protocols = self.protocol_service.get_item_protocols(self.selected_item_id)
            for protocol in protocols:
                self.item_protocol_table.insert(
                    "", "end", iid=f"usage-{protocol['id']}",
                    values=(protocol["id"], protocol["name"]),
                )
            stripe_rows(self.item_protocol_table)
            show_empty_state(self.item_protocol_table, "这件物品尚未关联 Protocol。")
        except Exception as error:
            self._display_error("读取物品的 Protocol", error)

    def open_item_protocol(self) -> None:
        selection = self.item_protocol_table.selection()
        if not selection:
            messagebox.showwarning("未选择 Protocol", "请先选择要打开的 Protocol。")
            return
        try:
            protocol_id = int(self.item_protocol_table.item(selection[0], "values")[0])
            if self.protocol_panel.open_protocol(protocol_id):
                self.notebook.select(self.protocol_panel)
        except Exception as error:
            self._display_error("打开 Protocol", error)

    # ---------- 位置操作 ----------

    def _selected_parent_id(self) -> int | None:
        return self.parent_by_label.get(self.location_parent_var.get())

    def add_location(self) -> None:
        try:
            self.location_service.create_location(
                self.location_name_var.get(),
                self._selected_parent_id(),
                self._get_text(self.location_notes_text),
            )
            self.clear_location_form()
            self.refresh_all()
            messagebox.showinfo("添加成功", "位置已保存。")
        except Exception as error:
            self._display_error("添加位置", error)

    def update_location(self) -> None:
        if self.selected_location_id is None:
            messagebox.showwarning("未选择位置", "请先在位置树中选择要修改的位置。")
            return
        try:
            self.location_service.update_location(
                self.selected_location_id,
                self.location_name_var.get(),
                self._selected_parent_id(),
                self._get_text(self.location_notes_text),
            )
            self.clear_location_form()
            self.refresh_all()
            messagebox.showinfo("修改成功", "位置信息已更新。")
        except Exception as error:
            self._display_error("修改位置", error)

    def delete_location(self) -> None:
        if self.selected_location_id is None:
            messagebox.showwarning("未选择位置", "请先在位置树中选择要删除的位置。")
            return
        if not messagebox.askyesno("确认删除", "确定要删除所选位置吗？"):
            return
        try:
            self.location_service.delete_location(self.selected_location_id)
            self.clear_location_form()
            self.refresh_all()
            messagebox.showinfo("删除成功", "位置已删除。")
        except Exception as error:
            self._display_error("删除位置", error)

    def on_location_selected(self, _event: tk.Event) -> None:
        selection = self.location_tree.selection()
        if not selection:
            return
        values = self.location_tree.item(selection[0], "values")
        if not values:
            return
        try:
            location = self.location_service.get_location(int(values[0]))
            self.selected_location_id = location["id"]
            self.location_name_var.set(location["name"])
            self.location_parent_var.set(
                self.parent_label_by_id.get(location["parent_id"], NO_PARENT)
            )
            self.location_path_var.set(location["full_path"])
            self._set_text(self.location_notes_text, location["notes"])
        except Exception as error:
            self._display_error("读取位置", error)

    def clear_location_form(self) -> None:
        self.selected_location_id = None
        self.location_name_var.set("")
        self.location_parent_var.set(NO_PARENT)
        self.location_path_var.set("尚未选择位置")
        self._set_text(self.location_notes_text, "")
        for iid in self.location_tree.selection():
            self.location_tree.selection_remove(iid)
