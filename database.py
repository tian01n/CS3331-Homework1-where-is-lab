"""SQLite 数据访问层。只负责持久化，不包含界面逻辑。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator


class Database:
    """管理数据库连接、建表和参数化查询。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """为一次操作创建连接，并保证提交、回滚和关闭。"""
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """首次运行时创建数据库表和必要索引。"""
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                    parent_id INTEGER,
                    notes TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (parent_id) REFERENCES locations(id)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    primary_name TEXT NOT NULL CHECK (length(trim(primary_name)) > 0),
                    chinese_name TEXT NOT NULL DEFAULT '',
                    english_name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL CHECK (
                        category IN ('试剂', '抗体', '耗材', '样品', '仪器', '其他')
                    ),
                    notes TEXT NOT NULL DEFAULT '',
                    location_id INTEGER NOT NULL,
                    FOREIGN KEY (location_id) REFERENCES locations(id)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS item_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    alias TEXT NOT NULL CHECK (length(trim(alias)) > 0),
                    FOREIGN KEY (item_id) REFERENCES items(id)
                        ON UPDATE CASCADE ON DELETE CASCADE,
                    UNIQUE (item_id, alias)
                );

                CREATE INDEX IF NOT EXISTS idx_locations_parent
                    ON locations(parent_id);
                CREATE INDEX IF NOT EXISTS idx_items_location
                    ON items(location_id);
                CREATE INDEX IF NOT EXISTS idx_items_category
                    ON items(category);
                CREATE INDEX IF NOT EXISTS idx_aliases_item
                    ON item_aliases(item_id);

                CREATE TABLE IF NOT EXISTS protocols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                    steps TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS protocol_items (
                    protocol_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    PRIMARY KEY (protocol_id, item_id),
                    FOREIGN KEY (protocol_id) REFERENCES protocols(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES items(id)
                        ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS idx_protocol_items_item
                    ON protocol_items(item_id);

                CREATE TABLE IF NOT EXISTS protocol_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    protocol_id INTEGER NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    extraction_note TEXT NOT NULL DEFAULT '',
                    UNIQUE(protocol_id, stored_name)
                );
                """
            )

    # ---------- 位置 ----------

    def create_location(self, name: str, parent_id: int | None, notes: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO locations (name, parent_id, notes) VALUES (?, ?, ?)",
                (name, parent_id, notes),
            )
            return int(cursor.lastrowid)

    def update_location(
        self, location_id: int, name: str, parent_id: int | None, notes: str
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE locations
                SET name = ?, parent_id = ?, notes = ?
                WHERE id = ?
                """,
                (name, parent_id, notes, location_id),
            )
            return cursor.rowcount > 0

    def delete_location(self, location_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM locations WHERE id = ?", (location_id,)
            )
            return cursor.rowcount > 0

    def get_location(self, location_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, name, parent_id, notes FROM locations WHERE id = ?",
                (location_id,),
            ).fetchone()
            return dict(row) if row else None

    def location_exists(self, location_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM locations WHERE id = ?", (location_id,)
            ).fetchone()
            return row is not None

    def list_locations(self) -> list[dict]:
        """返回所有位置及其从根节点开始的完整路径。"""
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE location_paths(id, name, parent_id, notes, full_path) AS (
                    SELECT id, name, parent_id, notes, name
                    FROM locations
                    WHERE parent_id IS NULL
                    UNION ALL
                    SELECT l.id, l.name, l.parent_id, l.notes,
                           lp.full_path || ' > ' || l.name
                    FROM locations AS l
                    JOIN location_paths AS lp ON l.parent_id = lp.id
                )
                SELECT id, name, parent_id, notes, full_path
                FROM location_paths
                ORDER BY full_path COLLATE NOCASE, id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_location_path(self, location_id: int) -> str | None:
        """沿父节点向上查询，再拼成从根到当前位置的路径。"""
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH RECURSIVE ancestors(id, name, parent_id, depth) AS (
                    SELECT id, name, parent_id, 0
                    FROM locations
                    WHERE id = ?
                    UNION ALL
                    SELECT l.id, l.name, l.parent_id, ancestors.depth + 1
                    FROM locations AS l
                    JOIN ancestors ON ancestors.parent_id = l.id
                )
                SELECT name FROM ancestors ORDER BY depth DESC
                """,
                (location_id,),
            ).fetchall()
            if not rows:
                return None
            return " > ".join(row["name"] for row in rows)

    def is_descendant(self, location_id: int, candidate_id: int) -> bool:
        """判断 candidate_id 是否为 location_id 的任意层级子位置。"""
        with self.connect() as connection:
            row = connection.execute(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM locations WHERE parent_id = ?
                    UNION ALL
                    SELECT l.id
                    FROM locations AS l
                    JOIN descendants AS d ON l.parent_id = d.id
                )
                SELECT 1 FROM descendants WHERE id = ? LIMIT 1
                """,
                (location_id, candidate_id),
            ).fetchone()
            return row is not None

    def location_has_children(self, location_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM locations WHERE parent_id = ? LIMIT 1",
                (location_id,),
            ).fetchone()
            return row is not None

    def location_has_items(self, location_id: int) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM items WHERE location_id = ? LIMIT 1",
                (location_id,),
            ).fetchone()
            return row is not None

    # ---------- 物品及别名 ----------

    def create_item(self, data: dict, aliases: Iterable[str]) -> int:
        """在同一个事务中创建物品和全部别名。"""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO items (
                    primary_name, chinese_name, english_name,
                    category, notes, location_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["primary_name"],
                    data["chinese_name"],
                    data["english_name"],
                    data["category"],
                    data["notes"],
                    data["location_id"],
                ),
            )
            item_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO item_aliases (item_id, alias) VALUES (?, ?)",
                ((item_id, alias) for alias in aliases),
            )
            return item_id

    def update_item(self, item_id: int, data: dict, aliases: Iterable[str]) -> bool:
        """修改物品时整体替换别名，事务失败会完整回滚。"""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE items
                SET primary_name = ?, chinese_name = ?, english_name = ?,
                    category = ?, notes = ?, location_id = ?
                WHERE id = ?
                """,
                (
                    data["primary_name"],
                    data["chinese_name"],
                    data["english_name"],
                    data["category"],
                    data["notes"],
                    data["location_id"],
                    item_id,
                ),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                "DELETE FROM item_aliases WHERE item_id = ?", (item_id,)
            )
            connection.executemany(
                "INSERT INTO item_aliases (item_id, alias) VALUES (?, ?)",
                ((item_id, alias) for alias in aliases),
            )
            return True

    def delete_item(self, item_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0

    def get_item(self, item_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, primary_name, chinese_name, english_name,
                       category, notes, location_id
                FROM items
                WHERE id = ?
                """,
                (item_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            alias_rows = connection.execute(
                """
                SELECT alias FROM item_aliases
                WHERE item_id = ? ORDER BY id
                """,
                (item_id,),
            ).fetchall()
            result["aliases"] = [alias_row["alias"] for alias_row in alias_rows]

        result["location_path"] = self.get_location_path(result["location_id"])
        return result

    @staticmethod
    def _escape_like(value: str) -> str:
        """让搜索框中的百分号和下划线按普通字符处理。"""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def list_items(self, search_text: str = "", category: str | None = None) -> list[dict]:
        """按名称、别名、备注、类别和完整位置路径搜索物品。"""
        query = """
            WITH RECURSIVE location_paths(id, full_path) AS (
                SELECT id, name FROM locations WHERE parent_id IS NULL
                UNION ALL
                SELECT l.id, lp.full_path || ' > ' || l.name
                FROM locations AS l
                JOIN location_paths AS lp ON l.parent_id = lp.id
            )
            SELECT i.id, i.primary_name, i.chinese_name, i.english_name,
                   i.category, i.notes, i.location_id,
                   COALESCE(lp.full_path, '') AS location_path,
                   COALESCE((
                       SELECT GROUP_CONCAT(ordered_alias.alias, ', ')
                       FROM (
                           SELECT a.alias
                           FROM item_aliases AS a
                           WHERE a.item_id = i.id
                           ORDER BY a.id
                       ) AS ordered_alias
                   ), '') AS aliases
            FROM items AS i
            LEFT JOIN location_paths AS lp ON lp.id = i.location_id
            WHERE 1 = 1
        """
        parameters: list[object] = []

        cleaned_search = search_text.strip()
        if cleaned_search:
            pattern = f"%{self._escape_like(cleaned_search)}%"
            query += """
                AND (
                    LOWER(COALESCE(i.primary_name, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR LOWER(COALESCE(i.chinese_name, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR LOWER(COALESCE(i.english_name, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR LOWER(COALESCE(i.category, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR LOWER(COALESCE(i.notes, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR LOWER(COALESCE(lp.full_path, '')) LIKE LOWER(?) ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM item_aliases AS search_alias
                        WHERE search_alias.item_id = i.id
                          AND LOWER(search_alias.alias) LIKE LOWER(?) ESCAPE '\\'
                    )
                )
            """
            parameters.extend([pattern] * 7)

        if category:
            query += " AND i.category = ?"
            parameters.append(category)

        query += " ORDER BY i.primary_name COLLATE NOCASE, i.id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [dict(row) for row in rows]

    def list_item_aliases(self) -> dict[int, list[str]]:
        """批量读取真实别名列表，识别时不拆分显示用的拼接字符串。"""
        result: dict[int, list[str]] = {}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT item_id, alias FROM item_aliases ORDER BY id"
            ).fetchall()
        for row in rows:
            result.setdefault(row["item_id"], []).append(row["alias"])
        return result

    # ---------- Protocol 及多对多关联 ----------

    def create_protocol(
        self, name: str, steps: str, notes: str, item_ids: Iterable[int], files=()
    ) -> int:
        """正文和物品关联整体提交；任意关联失败则整体回滚。"""
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO protocols (name, steps, notes) VALUES (?, ?, ?)",
                (name, steps, notes),
            )
            protocol_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO protocol_items (protocol_id, item_id) VALUES (?, ?)",
                ((protocol_id, item_id) for item_id in item_ids),
            )
            self._insert_protocol_files(connection, protocol_id, files)
            return protocol_id

    def update_protocol(
        self, protocol_id: int, name: str, steps: str, notes: str,
        item_ids: Iterable[int], files=None,
    ) -> bool:
        """用一个事务替换正文与全部关联，失败时保留原有数据。"""
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE protocols SET name = ?, steps = ?, notes = ? WHERE id = ?",
                (name, steps, notes, protocol_id),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                "DELETE FROM protocol_items WHERE protocol_id = ?", (protocol_id,)
            )
            connection.executemany(
                "INSERT INTO protocol_items (protocol_id, item_id) VALUES (?, ?)",
                ((protocol_id, item_id) for item_id in item_ids),
            )
            if files is not None:
                connection.execute("DELETE FROM protocol_files WHERE protocol_id = ?", (protocol_id,))
                self._insert_protocol_files(connection, protocol_id, files)
            return True

    @staticmethod
    def _insert_protocol_files(connection, protocol_id, files):
        connection.executemany(
            """INSERT INTO protocol_files
               (protocol_id, original_name, stored_name, sha256, extraction_status, extraction_note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ((protocol_id, item["original_name"], item["stored_name"], item["sha256"],
              item["extraction_status"], item["extraction_note"]) for item in files),
        )

    def referenced_protocol_files(self) -> set[str]:
        with self.connect() as connection:
            return {row[0] for row in connection.execute("SELECT stored_name FROM protocol_files")}

    def delete_protocol(self, protocol_id: int) -> bool:
        """外键级联只删除关联，不删除物品或位置。"""
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM protocols WHERE id = ?", (protocol_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _linked_items(connection: sqlite3.Connection, protocol_id: int) -> list[dict]:
        """从物品和位置表读取当前值，不复制名称或位置到关联表。"""
        rows = connection.execute(
            """
            WITH RECURSIVE location_paths(id, full_path) AS (
                SELECT id, name FROM locations WHERE parent_id IS NULL
                UNION ALL
                SELECT l.id, lp.full_path || ' > ' || l.name
                FROM locations AS l
                JOIN location_paths AS lp ON l.parent_id = lp.id
            )
            SELECT i.id, i.primary_name, i.category, i.location_id,
                   COALESCE(lp.full_path, '') AS location_path
            FROM protocol_items AS pi
            JOIN items AS i ON i.id = pi.item_id
            LEFT JOIN location_paths AS lp ON lp.id = i.location_id
            WHERE pi.protocol_id = ?
            ORDER BY i.primary_name COLLATE NOCASE, i.id
            """,
            (protocol_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_protocol(self, protocol_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, name, steps, notes FROM protocols WHERE id = ?",
                (protocol_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["items"] = self._linked_items(connection, protocol_id)
            result["item_ids"] = [item["id"] for item in result["items"]]
            result["files"] = [dict(row) for row in connection.execute(
                "SELECT original_name, stored_name, sha256, extraction_status, extraction_note "
                "FROM protocol_files WHERE protocol_id = ? ORDER BY id", (protocol_id,)
            )]
            return result

    def list_protocols(self, search_text: str = "") -> list[dict]:
        pattern = f"%{self._escape_like(search_text.strip())}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.name, p.steps, p.notes,
                       (SELECT COUNT(*) FROM protocol_items AS pi
                        WHERE pi.protocol_id = p.id) AS item_count
                FROM protocols AS p
                WHERE LOWER(p.name) LIKE LOWER(?) ESCAPE '\\'
                   OR LOWER(p.steps) LIKE LOWER(?) ESCAPE '\\'
                   OR LOWER(p.notes) LIKE LOWER(?) ESCAPE '\\'
                ORDER BY p.name COLLATE NOCASE, p.id
                """,
                (pattern, pattern, pattern),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_item_protocols(self, item_id: int) -> list[dict]:
        """反向查询使用某件物品的所有 Protocol。"""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.name
                FROM protocols AS p
                JOIN protocol_items AS pi ON pi.protocol_id = p.id
                WHERE pi.item_id = ?
                ORDER BY p.name COLLATE NOCASE, p.id
                """,
                (item_id,),
            ).fetchall()
            return [dict(row) for row in rows]
