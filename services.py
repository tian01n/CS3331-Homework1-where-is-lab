"""业务逻辑层：集中进行输入校验和位置层级安全检查。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from database import Database
from matching import MatchTextSource, NameMatcher, normalize_match_text


CATEGORIES = ("试剂", "抗体", "耗材", "样品", "仪器", "其他")


class AppError(Exception):
    """可以直接以中文提示给用户的业务异常。"""


class ValidationError(AppError):
    """输入内容不符合要求。"""


class NotFoundError(AppError):
    """要操作的数据已经不存在。"""


class ConflictError(AppError):
    """操作会破坏已有的数据关系。"""


def normalize_aliases(aliases: str | Iterable[str]) -> list[str]:
    """拆分逗号或换行输入，去空白并按输入顺序去除完全重复项。"""
    if isinstance(aliases, str):
        values = re.split(r"[,，\r\n]+", aliases)
    else:
        values = list(aliases)

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


class LocationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_location(
        self, name: str, parent_id: int | None = None, notes: str = ""
    ) -> int:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValidationError("位置名称不能为空。")
        if parent_id is not None and not self.database.location_exists(parent_id):
            raise ValidationError("所选上级位置不存在，请重新选择。")
        return self.database.create_location(cleaned_name, parent_id, notes.strip())

    def update_location(
        self,
        location_id: int,
        name: str,
        parent_id: int | None = None,
        notes: str = "",
    ) -> None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValidationError("位置名称不能为空。")
        if not self.database.location_exists(location_id):
            raise NotFoundError("所选位置已不存在，请刷新后重试。")
        if parent_id == location_id:
            raise ValidationError("一个位置不能把自己设置为上级位置。")
        if parent_id is not None:
            if not self.database.location_exists(parent_id):
                raise ValidationError("所选上级位置不存在，请重新选择。")
            if self.database.is_descendant(location_id, parent_id):
                raise ValidationError("不能把自己的子位置设置为上级位置，否则会形成循环。")
        if not self.database.update_location(
            location_id, cleaned_name, parent_id, notes.strip()
        ):
            raise NotFoundError("所选位置已不存在，请刷新后重试。")

    def delete_location(self, location_id: int) -> None:
        if not self.database.location_exists(location_id):
            raise NotFoundError("所选位置已不存在，请刷新后重试。")
        if self.database.location_has_children(location_id):
            raise ConflictError("该位置还有子位置，请先删除或移动子位置。")
        if self.database.location_has_items(location_id):
            raise ConflictError("该位置仍存放物品，请先删除或移动这些物品。")
        if not self.database.delete_location(location_id):
            raise NotFoundError("所选位置已不存在，请刷新后重试。")

    def get_location(self, location_id: int) -> dict:
        location = self.database.get_location(location_id)
        if location is None:
            raise NotFoundError("所选位置已不存在，请刷新后重试。")
        location["full_path"] = self.database.get_location_path(location_id) or ""
        return location

    def list_locations(self) -> list[dict]:
        return self.database.list_locations()

    def get_location_path(self, location_id: int) -> str:
        path = self.database.get_location_path(location_id)
        if path is None:
            raise NotFoundError("所选位置已不存在，请刷新后重试。")
        return path


class ItemService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _validate_item(
        self,
        primary_name: str,
        chinese_name: str,
        english_name: str,
        category: str,
        notes: str,
        location_id: int | None,
    ) -> dict:
        cleaned_primary_name = primary_name.strip()
        if not cleaned_primary_name:
            raise ValidationError("物品主要名称不能为空。")
        if category not in CATEGORIES:
            raise ValidationError("物品类别无效，请从下拉列表中选择。")
        if location_id is None or not self.database.location_exists(location_id):
            raise ValidationError("必须选择一个有效位置。")
        return {
            "primary_name": cleaned_primary_name,
            "chinese_name": chinese_name.strip(),
            "english_name": english_name.strip(),
            "category": category,
            "notes": notes.strip(),
            "location_id": location_id,
        }

    def create_item(
        self,
        primary_name: str,
        chinese_name: str,
        english_name: str,
        aliases: str | Iterable[str],
        category: str,
        notes: str,
        location_id: int | None,
    ) -> int:
        data = self._validate_item(
            primary_name,
            chinese_name,
            english_name,
            category,
            notes,
            location_id,
        )
        return self.database.create_item(data, normalize_aliases(aliases))

    def update_item(
        self,
        item_id: int,
        primary_name: str,
        chinese_name: str,
        english_name: str,
        aliases: str | Iterable[str],
        category: str,
        notes: str,
        location_id: int | None,
    ) -> None:
        if self.database.get_item(item_id) is None:
            raise NotFoundError("所选物品已不存在，请刷新后重试。")
        data = self._validate_item(
            primary_name,
            chinese_name,
            english_name,
            category,
            notes,
            location_id,
        )
        if not self.database.update_item(item_id, data, normalize_aliases(aliases)):
            raise NotFoundError("所选物品已不存在，请刷新后重试。")

    def delete_item(self, item_id: int) -> None:
        protocols = self.database.list_item_protocols(item_id)
        if protocols:
            names = "、".join(
                f"{protocol['name']}（编号 {protocol['id']}）" for protocol in protocols
            )
            raise ConflictError(f"该物品仍被以下 Protocol 使用：{names}。请先解除关联。")
        if not self.database.delete_item(item_id):
            raise NotFoundError("所选物品已不存在，请刷新后重试。")

    def get_item(self, item_id: int) -> dict:
        item = self.database.get_item(item_id)
        if item is None:
            raise NotFoundError("所选物品已不存在，请刷新后重试。")
        return item

    def search_items(self, search_text: str = "", category: str | None = None) -> list[dict]:
        if category is not None and category not in CATEGORIES:
            raise ValidationError("类别筛选条件无效。")
        return self.database.list_items(search_text, category)


class ProtocolService:
    """校验 Protocol 输入；编辑中的物品选择不经过此层写入。"""

    def __init__(self, database: Database) -> None:
        self.database = database

    def _validate(self, name: str, item_ids: Iterable[int]) -> tuple[str, list[int]]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValidationError("Protocol 名称不能为空。")
        unique_ids: list[int] = []
        for item_id in item_ids:
            if not isinstance(item_id, int) or isinstance(item_id, bool):
                raise ValidationError("关联物品编号无效，请重新选择。")
            if item_id not in unique_ids:
                if self.database.get_item(item_id) is None:
                    raise ValidationError("所选关联物品已不存在，请移除后重新选择。")
                unique_ids.append(item_id)
        return cleaned_name, unique_ids

    def create_protocol(
        self, name: str, steps: str = "", notes: str = "",
        item_ids: Iterable[int] = (), files=(),
    ) -> int:
        from file_services import validate_file_metadata
        name, item_ids = self._validate(name, item_ids)
        # 正文不 strip，以原样保留中文、空格和换行。
        return self.database.create_protocol(name, steps, notes, item_ids, validate_file_metadata(files))

    def update_protocol(
        self, protocol_id: int, name: str, steps: str = "", notes: str = "",
        item_ids: Iterable[int] = (), files=None,
    ) -> None:
        from file_services import validate_file_metadata
        self.get_protocol(protocol_id)
        name, item_ids = self._validate(name, item_ids)
        if not self.database.update_protocol(
            protocol_id, name, steps, notes, item_ids,
            None if files is None else validate_file_metadata(files),
        ):
            raise NotFoundError("所选 Protocol 已不存在，请刷新后重试。")

    def delete_protocol(self, protocol_id: int) -> None:
        if not self.database.delete_protocol(protocol_id):
            raise NotFoundError("所选 Protocol 已不存在，请刷新后重试。")

    def get_protocol(self, protocol_id: int) -> dict:
        protocol = self.database.get_protocol(protocol_id)
        if protocol is None:
            raise NotFoundError("所选 Protocol 已不存在，请刷新后重试。")
        return protocol

    def search_protocols(self, search_text: str = "") -> list[dict]:
        return self.database.list_protocols(search_text)

    def get_item_protocols(self, item_id: int) -> list[dict]:
        return self.database.list_item_protocols(item_id)

    def search_available_items(self, search_text: str = "") -> list[dict]:
        """选择器仅按主要名、中文名、英文名或别名筛选。"""
        text = search_text.strip().casefold()
        rows = self.database.list_items()
        if not text:
            return rows
        return [
            row for row in rows
            if any(text in row[field].casefold() for field in (
                "primary_name", "chinese_name", "english_name", "aliases"
            ))
        ]

    @staticmethod
    def _normalize_match_text(text: str) -> str:
        """兼容全角字符、英文大小写、连续空格和跨行的英文名称。"""
        return normalize_match_text(text)

    def recognize_items(self, text: str) -> list[dict]:
        """字面包含或局部字符相似度 >60% 的只读候选；不建立关联。"""
        if not isinstance(text, str):
            raise ValidationError("待识别的 Protocol 正文必须是文字。")
        source = MatchTextSource(text)
        body = source.text
        if not body:
            return []
        rows = self.database.list_items()
        aliases = self.database.list_item_aliases()
        terms_by_item: dict[int, dict[str, str]] = {}
        owners: dict[str, set[int]] = {}
        for row in rows:
            terms: dict[str, str] = {}
            names = [row[field] for field in ("primary_name", "chinese_name", "english_name")]
            names.extend(aliases.get(row["id"], []))
            for name in names:
                term = self._normalize_match_text(name)
                if term:
                    terms.setdefault(term, name)
                    owners.setdefault(term, set()).add(row["id"])
            terms_by_item[row["id"]] = terms

        matcher = NameMatcher(body)
        matches = {}
        for term in owners:
            found = matcher.match(term)
            if found is not None:
                # 匹配使用归一化文字，显示依据必须取回原文，不能把正文伪装成小写。
                found["normalized_text"] = found["text"]
                start, end = source.source_span(found["start"], found["end"])
                found["source_start"], found["source_end"] = start, end
                found["text"] = text[start:end]
                matches[term] = found

        result = []
        for row in rows:
            terms = terms_by_item[row["id"]]
            matched = [term for term in terms if term in matches]
            if not matched:
                continue
            ambiguous = [terms[term] for term in matched if len(owners[term]) > 1]
            details = [dict(matches[term], name=terms[term]) for term in matched]
            best = max(details, key=lambda match: (
                match["similarity"], match["match_type"] == "exact", len(match["name"])
            ))
            candidate = dict(row)
            candidate["matched_names"] = [terms[term] for term in matched]
            candidate["ambiguous_names"] = ambiguous
            candidate["ambiguous"] = bool(ambiguous)
            candidate["match_details"] = details
            candidate["similarity"] = best["similarity"]
            candidate["match_type"] = best["match_type"]
            candidate["matched_text"] = best["text"]
            candidate["matched_name"] = best["name"]
            candidate["requires_review"] = bool(ambiguous) or best["match_type"] != "exact"
            candidate["context"] = text[max(0, best["source_start"] - 25):best["source_end"] + 35]
            result.append(candidate)
        result.sort(key=lambda row: (-row["similarity"], row["requires_review"], row["id"]))
        return result
