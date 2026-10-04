"""自动识别候选：勾选确认仅改变待保存关联，不直接写数据库。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from services import ProtocolService
from theme import COLORS, show_empty_state, stripe_rows


class RecognitionPanel(ttk.Frame):
    def __init__(self, master, service: ProtocolService,
                 get_text: Callable[[], str], get_linked: Callable[[], list[int]],
                 confirm: Callable[[list[int]], None]) -> None:
        super().__init__(master, padding=10)
        self.service = service
        self.get_text = get_text
        self.get_linked = get_linked
        self.confirm = confirm
        self.candidates: list[dict] = []
        self.checked_ids: set[int] = set()
        self.recognized_text: str | None = None
        self.status_var = tk.StringVar(value="在上方粘贴正文，稍等即可看到识别结果。")
        self.summary_var = tk.StringVar(value="粘贴正文，自动生成候选")
        self.detail_var = tk.StringVar(value="单击一行勾选/取消；相似、宽松包含或重名候选需你选择。")
        host = self
        host.columnconfigure(0, weight=1)
        host.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(host)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        toolbar.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(toolbar, textvariable=self.summary_var, wraplength=280, style="Muted.TLabel")
        self.status_label.grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        frame = ttk.Frame(host)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        columns = ("check", "name", "matched", "similarity", "category", "path", "status")
        self.table = ttk.Treeview(frame, columns=columns, show="headings", height=4,
                                  selectmode="browse")
        self.table.tag_configure("review", foreground=COLORS["warning"])
        for column, label, width in zip(
            columns, ("确认", "物品名称", "名称/别名 → 正文文字", "字符相似度", "类别", "完整位置路径", "提示"),
            (48, 160, 230, 90, 60, 230, 170),
        ):
            self.table.heading(column, text=label)
            self.table.column(column, width=width, minwidth=40,
                              stretch=column not in ("check", "similarity", "category"))
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.bind("<ButtonRelease-1>", self._clicked)
        self.table.bind("<space>", self._space)
        ttk.Button(toolbar, text="确认勾选结果", command=self.confirm_checked, style="Primary.TButton").grid(row=0, column=1, padx=3)
        ttk.Button(toolbar, text="重新识别", command=self.refresh).grid(row=0, column=2, padx=3)
        ttk.Button(toolbar, text="查看依据", command=self.show_match_details).grid(row=0, column=3, padx=(3, 0))
        self.bind("<Configure>", self._resize_labels, add="+")

    def show_match_details(self):
        messagebox.showinfo("匹配依据 · 请核对具体物品", self.detail_var.get())

    def _resize_labels(self, event):
        if event.widget is self:
            self.status_label.configure(wraplength=max(150, event.width - 365))

    def invalidate(self) -> None:
        self.recognized_text = None
        self.candidates = []
        self.checked_ids.clear()
        self.table.delete(*self.table.get_children())
        self.status_var.set("正文已更新，正在等待自动识别……")
        self.summary_var.set("正在等待识别…")
        show_empty_state(self.table, "正在等待识别…")
        self.detail_var.set("识别后请检查结果；遗漏的物品可以在“手动补充”中加入。")

    def refresh(self) -> None:
        text = self.get_text()
        old_rows = {row["id"]: row for row in self.candidates}
        old_ids = set(old_rows)
        old_checked = set(self.checked_ids)
        same_text = text == self.recognized_text
        try:
            candidates = self.service.recognize_items(text)
        except Exception:
            self.invalidate()
            self.status_var.set("暂时无法识别，请点击“重新识别”重试；也可手动补充。")
            self.summary_var.set("识别暂不可用，请重试")
            return
        self.candidates = candidates
        self.recognized_text = text
        linked = set(self.get_linked())
        self.checked_ids = {
            row["id"] for row in candidates if row["id"] not in linked and not row["requires_review"]
            and (not same_text or row["id"] not in old_ids or row["id"] in old_checked)
        }
        # 保留用户明确勾选的待核对候选，但首次出现时不默认勾选。
        if same_text:
            self.checked_ids.update(
                row["id"] for row in candidates if row["requires_review"]
                and old_rows.get(row["id"], {}).get("requires_review")
                and row["id"] in old_checked and row["id"] not in linked
            )
        self._render()
        if not text.strip():
            self.status_var.set("在上方粘贴正文，稍等即可看到识别结果。")
            self.summary_var.set("粘贴正文，自动生成候选")
        elif not candidates:
            self.status_var.set("未找到字面包含或字符相似度超过 60% 的已有物品，可手动补充。")
            self.summary_var.set("没有匹配到候选，可手动补充")
        else:
            review = sum(row["requires_review"] for row in candidates)
            suffix = f"；其中 {review} 件需核对并手动勾选" if review else ""
            self.status_var.set(f"识别到 {len(candidates)} 件候选物品{suffix}。确认后仍需点击保存。")
            self.summary_var.set(f"候选 {len(candidates)} 件 · {review} 件待核对")
        self.detail_var.set("宽松候选 ≠ 同一种物品。局部字符相似度须 >60%，确认后还需保存；未登记物品不会展示。")

    def _render(self) -> None:
        self.table.delete(*self.table.get_children())
        linked = set(self.get_linked())
        for row in self.candidates:
            item_id = row["id"]
            if item_id in linked:
                status = "已加入待保存关联"
            elif row["ambiguous"]:
                status = "重名，请人工选择"
            elif row["match_type"] == "fuzzy":
                status = "相似候选，请核对"
            elif row["match_type"] == "substring":
                status = "宽松包含，请核对"
            else:
                status = "待确认"
            self.table.insert("", "end", iid=f"recognized-{item_id}", tags=("review",) if row["requires_review"] else (), values=(
                "—" if item_id in linked else ("☑" if item_id in self.checked_ids else "☐"),
                row["primary_name"], f"{row['matched_name']} → {' '.join(row['matched_text'].split())}",
                f"{row['similarity']:.1%}", row["category"],
                row["location_path"], status,
            ))
        stripe_rows(self.table)
        show_empty_state(self.table, "候选物品会显示在这里\n输入正文后自动识别，仍需你核对确认。")

    def toggle(self, item_id: int) -> None:
        row = next((row for row in self.candidates if row["id"] == item_id), None)
        if row is None:
            return
        self.detail_var.set(
            f"依据：{row['matched_name']} ↔ {row['matched_text']}（字符相似度 {row['similarity']:.1%}）；"
            f"匹配上下文：{row['context']}" + (
            f"；重名名称/别名：{' / '.join(row['ambiguous_names'])}" if row["ambiguous"] else ""
        ))
        if item_id not in self.get_linked():
            if item_id in self.checked_ids:
                self.checked_ids.remove(item_id)
            else:
                self.checked_ids.add(item_id)
        self._render()
        self.table.selection_set(f"recognized-{item_id}")

    def _clicked(self, event) -> None:
        iid = self.table.identify_row(event.y)
        if iid:
            self.toggle(int(iid.removeprefix("recognized-")))

    def _space(self, _event) -> str:
        selected = self.table.selection()
        if selected:
            self.toggle(int(selected[0].removeprefix("recognized-")))
        return "break"

    def confirm_checked(self) -> None:
        if self.recognized_text != self.get_text():
            self.refresh()
            messagebox.showinfo("识别结果已更新", "正文发生变化，请检查新的识别结果后再次确认。")
            return
        ids = [row["id"] for row in self.candidates if row["id"] in self.checked_ids]
        if not ids:
            messagebox.showwarning("没有待确认物品", "请先勾选需要的候选物品；相似、宽松包含或重名候选不会默认勾选。")
            return
        self.confirm(ids)
        self.checked_ids.difference_update(ids)
        self.refresh()
        self.detail_var.set("已加入待保存关联。可继续手动补充，最后点击“保存新增”或“保存修改”。")
