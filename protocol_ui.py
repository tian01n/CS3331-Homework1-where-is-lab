"""Protocol 标签页：正文和关联先保留在表单中，点击保存后才写数据库。"""

from __future__ import annotations

import tkinter as tk
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from recognition_ui import RecognitionPanel
from file_services import ProtocolFileService
from protocol_reader import ImportPreview, ProtocolReader
from services import ItemService, NotFoundError, ProtocolService
from theme import ScrollableForm, initial_sash, show_empty_state, stripe_rows, style_text


class ProtocolPanel(ttk.Frame):
    """保持 Protocol 编辑功能独立，避免主界面文件过度膨胀。"""

    def __init__(
        self, master: ttk.Notebook, service: ProtocolService,
        item_service: ItemService, on_saved: Callable[[], None],
        display_error: Callable[[str, Exception], None],
    ) -> None:
        super().__init__(master, style="Page.TFrame")
        self.service = service
        self.item_service = item_service
        self.on_saved = on_saved
        self.display_error = display_error
        self.selected_protocol_id: int | None = None
        # 这是未保存的表单状态；正式关联始终由数据库保存。
        self.pending_item_ids: list[int] = []
        self.pending_files: list[dict] = []
        self.file_service = ProtocolFileService(service.database)
        self._import_in_progress = False
        self._import_queue = queue.Queue()
        self._import_after_id = None
        self.search_var = tk.StringVar()
        self.item_search_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="新建草稿")
        self.count_var = tk.StringVar()
        self._recognition_after_id: str | None = None
        self._saved_state: tuple = ("", "", "", (), ())
        self._applied_search = ""
        self._build_ui()
        self.steps_text.bind("<<Modified>>", self._on_steps_modified)
        self.refresh_protocols()
        self.refresh_item_views()

    @staticmethod
    def _table(parent: ttk.Frame, columns: tuple, headings: tuple, widths: tuple,
               height: int = 5, selectmode: str = "browse") -> ttk.Treeview:
        """为列表附带横向和纵向滚动条。"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        table = ttk.Treeview(
            parent, columns=columns, show="headings", height=height,
            selectmode=selectmode,
        )
        for column, heading, width in zip(columns, headings, widths):
            table.heading(column, text=heading)
            table.column(column, width=width, minwidth=40)
        table.column(columns[0], stretch=False)
        table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(parent, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(parent, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return table

    @staticmethod
    def _text(parent: ttk.Frame, height: int) -> tk.Text:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        text = tk.Text(parent, height=height, width=35, wrap="word", undo=True)
        style_text(text, size=11)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return text

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        search = ttk.Frame(self, padding=10)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="查找 Protocol", style="Section.TLabel").grid(row=0, column=0)
        entry = ttk.Entry(search, textvariable=self.search_var)
        entry.grid(row=0, column=1, sticky="ew", padx=6)
        entry.bind("<Return>", lambda _event: self.refresh_protocols())
        ttk.Button(search, text="搜索", command=self.refresh_protocols, style="Primary.TButton").grid(
            row=0, column=2, padx=4
        )
        ttk.Button(search, text="显示全部", command=self.show_all).grid(row=0, column=3)

        self.workspace_panes = ttk.Panedwindow(self, orient="horizontal")
        self.workspace_panes.grid(row=1, column=0, sticky="nsew")
        listing_card = ttk.Frame(self.workspace_panes, padding=16)
        listing_card.columnconfigure(0, weight=1)
        listing_card.rowconfigure(2, weight=1)
        self.workspace_panes.add(listing_card, weight=1)
        ttk.Label(listing_card, text="Protocol 清单", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(listing_card, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 12))
        listing = ttk.Frame(listing_card)
        listing.grid(row=2, column=0, sticky="nsew")
        self.protocol_table = self._table(
            listing, ("id", "name", "item_count"),
            ("编号", "名称", "物品数"), (50, 180, 60), height=12,
        )
        self.protocol_table.bind("<<TreeviewSelect>>", self.on_protocol_selected)

        # 名称、正文、关联页和操作按钮属于同一个可滚动的右侧编辑区。
        # 不再用上下分隔线把关联区挤成一条小框。
        self.editor_scroll = ScrollableForm(self.workspace_panes, width=700, height=480, padding=12)
        self.workspace_panes.add(self.editor_scroll, weight=3)
        form = self.editor_scroll.content
        initial_sash(self.workspace_panes, 0.25)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(3, weight=1)
        ttk.Label(form, textvariable=self.mode_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        name_frame = ttk.Frame(form)
        name_frame.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        name_frame.columnconfigure(1, weight=1)
        ttk.Label(name_frame, text="Protocol 名称 *").grid(row=0, column=0)
        ttk.Entry(name_frame, textvariable=self.name_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )
        body_toolbar = ttk.Frame(form)
        body_toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(body_toolbar, text="实验步骤正文", style="Muted.TLabel").pack(side="left")
        ttk.Button(body_toolbar, text="放大阅读", command=self.open_reader, style="Primary.TButton").pack(side="right", padx=4)
        self.import_button = ttk.Button(body_toolbar, text="导入 Protocol 文件", command=self.import_file)
        self.import_button.pack(side="right", padx=4)
        self.steps_frame = ttk.Frame(form)
        self.steps_frame.grid(row=3, column=0, sticky="nsew")
        self.steps_text = self._text(self.steps_frame, 9)
        self.steps_text.configure(spacing3=5)

        self.association_tabs = ttk.Notebook(form)
        self.association_tabs.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.recognition_panel = RecognitionPanel(
            self.association_tabs, self.service,
            lambda: self.steps_text.get("1.0", "end-1c"),
            lambda: list(self.pending_item_ids), self.confirm_recognized_items,
        )
        self.manual_tab = ttk.Frame(self.association_tabs, padding=6)
        self.confirmed_tab = ttk.Frame(self.association_tabs, padding=6)
        manual = self.manual_tab
        confirmed = self.confirmed_tab
        self.association_tabs.add(self.recognition_panel, text="自动识别")
        self.association_tabs.add(manual, text="手动补充")
        self.association_tabs.add(confirmed, text="已确认物品 (0)")
        self.files_tab = ttk.Frame(self.association_tabs, padding=6)
        self.association_tabs.add(self.files_tab, text="原始文件 (0)")
        self.notes_tab = ttk.Frame(self.association_tabs, padding=12)
        notes_pane = self.notes_tab
        notes_pane.columnconfigure(0, weight=1)
        notes_pane.rowconfigure(1, weight=1)
        ttk.Label(notes_pane, text="补充说明、使用提示或需要核对的事项。", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        notes_frame = ttk.Frame(notes_pane)
        notes_frame.grid(row=1, column=0, sticky="nsew")
        self.notes_text = self._text(notes_frame, 3)
        self.association_tabs.add(notes_pane, text="备注")
        files = self.files_tab
        files.columnconfigure(0, weight=1)
        files.rowconfigure(1, weight=1)
        ttk.Label(files, text="保留本地原件；导入后还需点击保存 Protocol。", wraplength=500).grid(
            row=0, column=0, sticky="ew", pady=(0, 4)
        )
        file_frame = ttk.Frame(files)
        file_frame.grid(row=1, column=0, sticky="nsew")
        self.file_table = self._table(
            file_frame, ("name", "status", "note"), ("文件名", "文字提取状态", "说明"),
            (210, 120, 420), height=5,
        )
        file_actions = ttk.Frame(files)
        file_actions.grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(file_actions, text="打开原始文件", command=self.open_selected_file).pack(side="left", padx=4)
        ttk.Button(file_actions, text="移除附件关联", command=self.remove_selected_file, style="Danger.TButton").pack(side="left", padx=4)
        for pane in (manual, confirmed):
            pane.columnconfigure(0, weight=1)
            pane.rowconfigure(2, weight=1)
        ttk.Label(manual, text="识别有遗漏时，用名称或别名搜索；Ctrl / Shift 多选。").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        item_search = ttk.Frame(manual)
        item_search.grid(row=1, column=0, sticky="ew")
        item_search.columnconfigure(0, weight=1)
        item_entry = ttk.Entry(item_search, textvariable=self.item_search_var)
        item_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        item_entry.bind("<Return>", lambda _event: self.refresh_item_views())
        ttk.Button(item_search, text="搜索物品", command=self.refresh_item_views).grid(
            row=0, column=1
        )
        available_frame = ttk.Frame(manual)
        available_frame.grid(row=2, column=0, sticky="nsew", pady=3)
        item_columns = ("id", "name", "category", "path")
        item_headings = ("编号", "物品名称", "类别", "完整位置路径")
        item_widths = (50, 150, 60, 240)
        self.available_table = self._table(
            available_frame, item_columns, item_headings, item_widths,
            height=5, selectmode="extended",
        )
        ttk.Button(manual, text="加入已选物品 ↓", command=self.add_selected_items, style="Primary.TButton").grid(
            row=3, column=0, sticky="w", pady=2
        )
        ttk.Label(confirmed, text="确认和手动补充的物品在此汇总；点击保存才生效。").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        selected_frame = ttk.Frame(confirmed)
        selected_frame.grid(row=2, column=0, sticky="nsew")
        self.selected_table = self._table(
            selected_frame, item_columns, item_headings, item_widths,
            height=5, selectmode="extended",
        )
        ttk.Button(confirmed, text="移除已选物品", command=self.remove_selected_items, style="Danger.TButton").grid(
            row=3, column=0, sticky="w", pady=3
        )
        self.editor_actions = ttk.Frame(form)
        buttons = self.editor_actions
        buttons.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.action_buttons = []
        actions = (
            ("新建 / 清空", self.clear_form),
            ("保存新增", self.add_protocol),
            ("保存修改", self.update_protocol),
            ("删除", self.delete_protocol),
            ("取消编辑", self.cancel_edit),
        )
        for column, (label, command) in enumerate(actions):
            buttons.columnconfigure(column, weight=1)
            style = "Primary.TButton" if label in ("保存新增", "保存修改") else (
                "Danger.TButton" if label == "删除" else "TButton")
            button = ttk.Button(buttons, text=label, command=command, style=style)
            button.grid(
                row=0, column=column, sticky="ew", padx=2
            )
            self.action_buttons.append(button)
        self.editor_scroll.bind_wheel(scroll_nested=True)

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.edit_reset()
        widget.edit_modified(False)

    @staticmethod
    def _clear_table(table: ttk.Treeview) -> None:
        for iid in table.get_children():
            table.delete(iid)

    def refresh_protocols(self, force: bool = False) -> None:
        """保留仍显示的选中编号；筛选掉当前记录则清除编辑状态。"""
        try:
            requested_search = self.search_var.get()
            rows = self.service.search_protocols(requested_search)
            selected_id = self.selected_protocol_id
            if selected_id is not None and not any(row["id"] == selected_id for row in rows):
                if not force and not self.confirm_discard_changes():
                    self.search_var.set(self._applied_search)
                    return
                self.clear_form(force=True)
                selected_id = None
                # 提醒中可能保存了改名，因此重新查询。
                self.search_var.set(requested_search)
                rows = self.service.search_protocols(self.search_var.get())
            self._applied_search = self.search_var.get()
            self._clear_table(self.protocol_table)
            for row in rows:
                self.protocol_table.insert(
                    "", "end", iid=f"protocol-{row['id']}",
                    values=(row["id"], row["name"], row["item_count"]),
                )
            stripe_rows(self.protocol_table)
            self.count_var.set(f"当前显示 {len(rows)} 份")
            show_empty_state(self.protocol_table, "没有匹配的 Protocol\n换个关键词试试。" if self.search_var.get().strip() else
                             "还没有 Protocol\n在右侧粘贴正文，或导入已有实验文件。")
            if selected_id is not None:
                if any(row["id"] == selected_id for row in rows):
                    self.protocol_table.selection_set(f"protocol-{selected_id}")
        except Exception as error:
            self.display_error("搜索 Protocol", error)

    def show_all(self) -> None:
        self.search_var.set("")
        self.refresh_protocols()

    def refresh_item_views(self) -> None:
        """更新名称和路径，同时保留未保存的关联选择及正文。"""
        try:
            rows = self.service.search_available_items(self.item_search_var.get())
            self._clear_table(self.available_table)
            for row in rows:
                self.available_table.insert(
                    "", "end", iid=f"available-{row['id']}",
                    values=(row["id"], row["primary_name"], row["category"],
                            row["location_path"]),
                )
            stripe_rows(self.available_table)
            show_empty_state(self.available_table, "没有可选物品\n请先录入物品，或换个名称搜索。")
            self._refresh_selected_items()
            self.recognition_panel.refresh()
        except Exception as error:
            self.display_error("刷新关联物品", error)

    def _refresh_selected_items(self) -> None:
        self._clear_table(self.selected_table)
        show_empty_state(self.selected_table, "还没有确认物品\n核对自动候选，或从“手动补充”加入。")
        for item_id in self.pending_item_ids:
            try:
                item = self.item_service.get_item(item_id)
                values = (item_id, item["primary_name"], item["category"],
                          item["location_path"])
            except NotFoundError:
                values = (item_id, "物品已不存在，请移除", "", "")
            self.selected_table.insert(
                "", "end", iid=f"selected-{item_id}", values=values
            )
        stripe_rows(self.selected_table)
        show_empty_state(self.selected_table, "还没有确认物品\n核对自动候选，或从“手动补充”加入。")
        self.association_tabs.tab(self.confirmed_tab, text=f"已确认物品 ({len(self.pending_item_ids)})")

    def add_selected_items(self) -> None:
        selected = self.available_table.selection()
        if not selected:
            messagebox.showwarning("未选择物品", "请先在候选列表中选择一个或多个物品。")
            return
        try:
            for iid in selected:
                item_id = int(self.available_table.item(iid, "values")[0])
                if item_id not in self.pending_item_ids:
                    self.pending_item_ids.append(item_id)
            self._refresh_selected_items()
            self.recognition_panel.refresh()
        except Exception as error:
            self.display_error("选择物品", error)

    def remove_selected_items(self) -> None:
        selected = self.selected_table.selection()
        if not selected:
            messagebox.showwarning("未选择物品", "请先在已选列表中选择要移除的物品。")
            return
        try:
            removed_ids = {
                int(self.selected_table.item(iid, "values")[0]) for iid in selected
            }
            self.pending_item_ids = [
                item_id for item_id in self.pending_item_ids if item_id not in removed_ids
            ]
            self._refresh_selected_items()
            self.recognition_panel.refresh()
        except Exception as error:
            self.display_error("移除物品", error)

    def _form_values(self) -> dict:
        return {
            "name": self.name_var.get(),
            "steps": self.steps_text.get("1.0", "end-1c"),
            "notes": self.notes_text.get("1.0", "end-1c"),
            "item_ids": list(self.pending_item_ids),
            "files": list(self.pending_files),
        }

    def _save_current(self, as_new: bool = False) -> bool:
        if self._import_in_progress:
            messagebox.showinfo("文件正在导入", "请等待导入预览完成后再保存。")
            return False
        try:
            self.file_service.promote(self.pending_files)
            if as_new or self.selected_protocol_id is None:
                protocol_id = self.service.create_protocol(**self._form_values())
            else:
                protocol_id = self.selected_protocol_id
                self.service.update_protocol(protocol_id, **self._form_values())
            self.open_protocol(protocol_id, force=True)
            self.on_saved()
            return True
        except Exception as error:
            self.display_error("保存 Protocol", error)
            return False

    def add_protocol(self) -> None:
        if self._save_current(as_new=True):
            messagebox.showinfo("添加成功", "Protocol 及物品关联已保存。")

    def _has_selection(self) -> bool:
        selection = self.protocol_table.selection()
        return (
            self.selected_protocol_id is not None
            and f"protocol-{self.selected_protocol_id}" in selection
        )

    def update_protocol(self) -> None:
        if not self._has_selection():
            messagebox.showwarning("未选择 Protocol", "请先在列表中选择要修改的 Protocol。")
            return
        if self._save_current():
            messagebox.showinfo("修改成功", "Protocol 及物品关联已更新。")

    def delete_protocol(self) -> None:
        if self._import_in_progress:
            messagebox.showinfo("文件正在导入", "请等待导入预览完成后再删除记录。")
            return
        if not self._has_selection():
            messagebox.showwarning("未选择 Protocol", "请先在列表中选择要删除的 Protocol。")
            return
        if not messagebox.askyesno("确认删除", "确定删除所选 Protocol？关联物品会保留。"):
            return
        try:
            self.service.delete_protocol(self.selected_protocol_id)
            self.clear_form(force=True)
            self.refresh_protocols()
            self.on_saved()
            messagebox.showinfo("删除成功", "Protocol 已删除，物品与位置仍保留。")
        except Exception as error:
            self.display_error("删除 Protocol", error)

    def _load_protocol(self, protocol: dict) -> None:
        self.file_service.cleanup_uncommitted()
        self.selected_protocol_id = protocol["id"]
        self.mode_var.set(f"编辑 Protocol（编号：{protocol['id']}）")
        self.name_var.set(protocol["name"])
        self._set_text(self.steps_text, protocol["steps"])
        self._set_text(self.notes_text, protocol["notes"])
        self.pending_item_ids = list(protocol["item_ids"])
        self.pending_files = list(protocol.get("files", []))
        self._refresh_files()
        self._refresh_selected_items()
        self._saved_state = self._state()
        self._cancel_recognition()
        self.recognition_panel.invalidate()
        self.recognition_panel.refresh()

    def open_protocol(self, protocol_id: int, force: bool = False) -> bool:
        """反向关联入口也通过编号打开，取消编辑后可恢复保存状态。"""
        protocol = self.service.get_protocol(protocol_id)
        if not force:
            if protocol_id == self.selected_protocol_id:
                return True
            if not self.confirm_discard_changes():
                return False
        self.search_var.set("")
        self._load_protocol(protocol)
        self.refresh_protocols(force=True)
        self.protocol_table.see(f"protocol-{protocol_id}")
        return True

    def on_protocol_selected(self, _event: tk.Event) -> None:
        selection = self.protocol_table.selection()
        if not selection:
            if self.selected_protocol_id is not None:
                if not self.clear_form():
                    self._restore_selection()
            return
        protocol_id = int(self.protocol_table.item(selection[0], "values")[0])
        # 刷新时恢复同一个编号，不重新加载正文，避免丢失尚未保存的修改。
        if protocol_id == self.selected_protocol_id:
            return
        if not self.confirm_discard_changes():
            self._restore_selection()
            return
        try:
            self._load_protocol(self.service.get_protocol(protocol_id))
            self.protocol_table.selection_set(f"protocol-{protocol_id}")
        except Exception as error:
            self.display_error("读取 Protocol", error)

    def cancel_edit(self) -> None:
        """取消只重新读取或清空表单，不调用任何数据库写入函数。"""
        if self._import_in_progress:
            messagebox.showinfo("文件正在导入", "请等待导入预览完成，或在预览中取消导入。")
            return
        try:
            if self.selected_protocol_id is None:
                self.clear_form(force=True)
            else:
                self._load_protocol(self.service.get_protocol(self.selected_protocol_id))
        except Exception as error:
            self.display_error("取消编辑", error)

    def clear_form(self, force: bool = False) -> bool:
        if not force and not self.confirm_discard_changes():
            return False
        self.file_service.cleanup_uncommitted()
        self._cancel_recognition()
        self.selected_protocol_id = None
        self.pending_item_ids = []
        self.pending_files = []
        self._refresh_files()
        self.mode_var.set("新建草稿")
        self.name_var.set("")
        self._set_text(self.steps_text, "")
        self._set_text(self.notes_text, "")
        self._refresh_selected_items()
        for iid in self.protocol_table.selection():
            self.protocol_table.selection_remove(iid)
        self._saved_state = self._state()
        self.recognition_panel.invalidate()
        self.recognition_panel.refresh()
        return True

    def _state(self) -> tuple:
        values = self._form_values()
        return (values["name"], values["steps"], values["notes"],
                tuple(sorted(set(values["item_ids"]))),
                tuple(sorted(item["stored_name"] for item in self.pending_files)))

    def has_unsaved_changes(self) -> bool:
        return self._state() != self._saved_state

    def confirm_discard_changes(self) -> bool:
        if self._import_in_progress:
            messagebox.showinfo("文件正在导入", "请等待文字提取和导入预览完成后再切换或关闭。")
            return False
        if not self.has_unsaved_changes():
            return True
        decision = messagebox.askyesnocancel(
            "Protocol 有未保存修改",
            "当前 Protocol 有未保存的正文或关联。\n\n"
            "是：保存后继续\n否：放弃修改继续\n取消：留在当前编辑内容",
        )
        if decision is None:
            return False
        if decision:
            return self._save_current()
        return True

    def _restore_selection(self) -> None:
        if self.selected_protocol_id is not None:
            iid = f"protocol-{self.selected_protocol_id}"
            if self.protocol_table.exists(iid):
                self.protocol_table.selection_set(iid)
                return
        for iid in self.protocol_table.selection():
            self.protocol_table.selection_remove(iid)

    def confirm_recognized_items(self, ids: list[int]) -> None:
        for item_id in ids:
            if item_id not in self.pending_item_ids:
                self.pending_item_ids.append(item_id)
        self._refresh_selected_items()

    def _on_steps_modified(self, _event) -> None:
        if not self.steps_text.edit_modified():
            return
        self.steps_text.edit_modified(False)
        self._cancel_recognition()
        self.recognition_panel.invalidate()
        self._recognition_after_id = self.after(500, self._auto_recognize)

    def _auto_recognize(self) -> None:
        self._recognition_after_id = None
        self.recognition_panel.refresh()

    def _cancel_recognition(self) -> None:
        if self._recognition_after_id is not None:
            self.after_cancel(self._recognition_after_id)
            self._recognition_after_id = None

    def destroy(self) -> None:
        self._cancel_recognition()
        if self._import_after_id is not None:
            self.after_cancel(self._import_after_id)
        try:
            self.file_service.cleanup_uncommitted()
        except Exception:
            # 崩溃/数据库被占用时保留待导入副本，不冒险删除正式文件。
            pass
        super().destroy()

    def _refresh_files(self):
        self._clear_table(self.file_table)
        labels = {"ok": "已提取文字", "partial": "部分页缺少文字", "needs_ocr": "可能需要 OCR",
                  "empty": "没有正文文字", "error": "提取失败", "unavailable": "组件不可用"}
        for item in self.pending_files:
            self.file_table.insert("", "end", iid=item["stored_name"], values=(
                item["original_name"], labels.get(item["extraction_status"], "未知"), item["extraction_note"],
            ))
        stripe_rows(self.file_table)
        show_empty_state(self.file_table, "还没有原始文件\n点击上方“导入 Protocol 文件”添加附件。")
        self.association_tabs.tab(self.files_tab, text=f"原始文件 ({len(self.pending_files)})")

    def import_file(self):
        if self._import_in_progress:
            return
        source = filedialog.askopenfilename(
            title="导入 Protocol（仅保存到本地，不上传网络）",
            filetypes=[("Protocol 文件", "*.docx *.doc *.pdf *.txt *.md"), ("所有文件", "*.*")],
        )
        if not source:
            return
        self._import_in_progress = True
        self.import_button.state(["disabled"])
        self.import_button.configure(text="正在读取文件…")

        def worker():
            try:
                self._import_queue.put((True, self.file_service.stage_import(source)))
            except Exception as error:
                self._import_queue.put((False, error))

        threading.Thread(target=worker, daemon=True).start()
        self._import_after_id = self.after(100, self._poll_import)

    def _poll_import(self):
        self._import_after_id = None
        try:
            successful, result = self._import_queue.get_nowait()
        except queue.Empty:
            self._import_after_id = self.after(100, self._poll_import)
            return
        # 预览窗口是模态窗口，预览关闭后才允许切换记录。
        try:
            if not successful:
                self.display_error("导入 Protocol 文件", result)
                return
            if any(item["sha256"] == result["file"]["sha256"] for item in self.pending_files):
                self.file_service.cleanup_uncommitted([result["file"]["stored_name"]])
                messagebox.showinfo("文件已存在", "当前 Protocol 已经添加过相同内容的文件，不重复导入。")
                return
            choice = ImportPreview.ask(self, result)
            self.apply_import_result(result, choice)
        finally:
            self._import_in_progress = False
            self.import_button.state(["!disabled"])
            self.import_button.configure(text="导入 Protocol 文件")

    def apply_import_result(self, result, choice):
        metadata, text = result["file"], result["text"]
        if choice not in ("replace", "append", "attachment"):
            self.file_service.cleanup_uncommitted([metadata["stored_name"]])
            return False
        if any(item["sha256"] == metadata["sha256"] for item in self.pending_files):
            self.file_service.cleanup_uncommitted([metadata["stored_name"]])
            return False
        if choice in ("replace", "append") and not text.strip():
            self.file_service.cleanup_uncommitted([metadata["stored_name"]])
            messagebox.showwarning("没有可用文字", "提取失败或扫描件不能覆盖正文，请选择仅保存附件。")
            return False
        existing = self.steps_text.get("1.0", "end-1c")
        if choice == "replace" and existing.strip() and not messagebox.askyesno(
            "确认替换正文", "这会替换当前编辑框里的正文（尚未写入数据库）。确定继续吗？",
        ):
            self.file_service.cleanup_uncommitted([metadata["stored_name"]])
            return False
        self.pending_files.append(metadata)
        if not self.name_var.get().strip():
            self.name_var.set(Path(metadata["original_name"]).stem)
        if choice in ("replace", "append"):
            self._set_text(self.steps_text, text if choice == "replace" or not existing else existing + "\n\n" + text)
            self._cancel_recognition()
            self.recognition_panel.invalidate()
            self.recognition_panel.refresh()
            self.association_tabs.select(self.recognition_panel)
        else:
            self.association_tabs.select(self.files_tab)
        self._refresh_files()
        return True

    def _selected_file(self):
        selected = self.file_table.selection()
        if not selected:
            messagebox.showwarning("未选择文件", "请先选择一份原始文件。")
            return None
        return next(item for item in self.pending_files if item["stored_name"] == selected[0])

    def open_selected_file(self):
        item = self._selected_file()
        if item is not None:
            self.open_original_file(item)

    def open_original_file(self, item):
        try:
            self.file_service.open_file(item)
        except Exception as error:
            self.display_error("打开原始文件", error)

    def remove_selected_file(self):
        item = self._selected_file()
        if item is not None:
            self.pending_files.remove(item)
            self._refresh_files()
            # 不删除正式磁盘副本；取消编辑仍能恢复，其他 Protocol 也可继续引用。

    def open_reader(self):
        return ProtocolReader(
            self, self.name_var.get(), self.steps_text.get("1.0", "end-1c"),
            self.notes_text.get("1.0", "end-1c"), self.pending_files,
            self.open_original_file, dirty=self.has_unsaved_changes(),
        )
