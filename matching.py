"""本地宽松字符匹配：只产生候选，不判断物品是否为同一种产品。"""

from __future__ import annotations

import re
import unicodedata
from array import array
from difflib import SequenceMatcher


SIMILARITY_THRESHOLD = 0.60
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff"
_TOKENS = re.compile(rf"[a-z0-9_]+|[{_CJK}]+|[\u0370-\u03ff]+|[^\s]")
_CHINESE = re.compile(rf"^[{_CJK}]+$")
_SEPARATOR = re.compile(r"[,，、;；。!?！？:：]")
_ASCII_WORD = re.compile(r"[a-z0-9_]")


def normalize_match_text(text: str) -> str:
    """仅用于比较；原文显示不能使用这个经过大小写折叠的副本。"""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class MatchTextSource:
    """比较文字与原文位置的映射，兼容大小写扩展、全角和跨行文字。"""

    def __init__(self, source: str) -> None:
        self.starts = array("I")
        self.ends = array("I")
        characters = []
        pending_space = None
        for piece, start, end in self._pieces(source):
            for character in piece.casefold():
                if character.isspace():
                    pending_space = (pending_space[0] if pending_space else start, end)
                    continue
                if pending_space and characters:
                    characters.append(" ")
                    self.starts.append(pending_space[0])
                    self.ends.append(pending_space[1])
                pending_space = None
                characters.append(character)
                self.starts.append(start)
                self.ends.append(end)
        self.text = "".join(characters)

    @staticmethod
    def _pieces(source: str):
        if not source:
            return
        start = 0
        piece = unicodedata.normalize("NFKC", source[0])
        for index in range(1, len(source)):
            following = unicodedata.normalize("NFKC", source[index])
            # 合并附加符号及可跨边界组合的字符（如韩文音节），避免位置偏移。
            joins = bool(piece and following) and (
                unicodedata.category(following[0]).startswith("M")
                or unicodedata.normalize("NFC", piece[-1] + following[0]) != piece[-1] + following[0]
            )
            if joins:
                piece = unicodedata.normalize("NFKC", source[start:index + 1])
            else:
                yield piece, start, index
                start, piece = index, following
        yield piece, start, len(source)

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        """把非空的比较片段定位回输入原文；不能直接复用归一化下标。"""
        if start < 0 or end <= start or end > len(self.starts):
            raise ValueError("匹配片段的位置无效。")
        return self.starts[start], self.ends[end - 1]


class NameMatcher:
    """对名称与局部文字比较，避免把名称与整篇长正文计算相似度。"""

    def __init__(self, body: str) -> None:
        self.body = body
        self.tokens = list(_TOKENS.finditer(body))
        self.fragment_cache: dict[int, list[tuple[str, int, int]]] = {}

    def _fragments(self, length: int) -> list[tuple[str, int, int]]:
        if length in self.fragment_cache:
            return self.fragment_cache[length]
        # 2*M/(len(name)+len(fragment)) > 0.6 的必要长度条件。
        minimum = (3 * length) // 7 + 1
        maximum = (7 * length - 1) // 3
        fragments: dict[str, tuple[str, int, int]] = {}
        for index, token in enumerate(self.tokens):
            if _SEPARATOR.search(token.group()):
                continue
            for following_index in range(index, len(self.tokens)):
                following = self.tokens[following_index]
                if _SEPARATOR.search(following.group()):
                    break
                start, end = token.start(), following.end()
                size = end - start
                if size > maximum:
                    break
                if size >= minimum:
                    value = self.body[start:end]
                    fragments.setdefault(value, (value, start, end))
            # 中文没有空格分词，增加连续汉字局部片段，如“离心后弃上清”中的“离心”。
            if _CHINESE.fullmatch(token.group()):
                for offset in range(len(token.group())):
                    start = token.start() + offset
                    for size in range(minimum, min(maximum, token.end() - start) + 1):
                        end = start + size
                        value = self.body[start:end]
                        fragments.setdefault(value, (value, start, end))
        result = list(fragments.values())
        # 避免许多不同长度的名称同时保留大量片段；正文和匹配结果不截断。
        if len(self.fragment_cache) >= 4:
            self.fragment_cache.pop(next(iter(self.fragment_cache)))
        self.fragment_cache[length] = result
        return result

    def match(self, term: str) -> dict | None:
        if not term:
            return None
        start = self.body.find(term)
        contained = None
        while start >= 0:
            end = start + len(term)
            # 边界只用于标注宽松包含，不再阻止展示候选。
            attached = (
                bool(_ASCII_WORD.fullmatch(term[0])) and start > 0
                and bool(_ASCII_WORD.fullmatch(self.body[start - 1]))
            ) or (
                bool(_ASCII_WORD.fullmatch(term[-1])) and end < len(self.body)
                and bool(_ASCII_WORD.fullmatch(self.body[end]))
            )
            detail = {"text": self.body[start:end], "start": start, "end": end,
                      "similarity": 1.0, "match_type": "substring" if attached else "exact"}
            if not attached:
                return detail
            if contained is None:
                contained = detail
            start = self.body.find(term, start + 1)
        if contained is not None:
            return contained

        matcher = SequenceMatcher(None, "", term, autojunk=False)
        best = None
        for fragment, start, end in self._fragments(len(term)):
            matcher.set_seq1(fragment)
            if matcher.quick_ratio() <= SIMILARITY_THRESHOLD:
                continue
            similarity = matcher.ratio()
            if similarity <= SIMILARITY_THRESHOLD:
                continue
            if best is None or similarity > best["similarity"]:
                best = {"text": fragment, "start": start, "end": end,
                        "similarity": similarity, "match_type": "fuzzy"}
        return best
