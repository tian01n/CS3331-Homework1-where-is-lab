"""原文件副本、离线文字提取和待保存附件；不依赖原来的磁盘路径。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from dependencies import optional_module
from services import ValidationError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
EXTENSIONS = {".docx", ".doc", ".pdf", ".txt", ".md"}
STATUSES = {"ok", "partial", "needs_ocr", "empty", "error", "unavailable"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def validate_file_metadata(files):
    result = []
    seen = set()
    for item in files:
        stored = item.get("stored_name", "")
        if not isinstance(stored, str) or not re.fullmatch(r"[0-9a-f]{32}\.(docx|doc|pdf|txt|md)", stored):
            raise ValidationError("附件存储名称无效。")
        if stored in seen:
            continue
        seen.add(stored)
        original = item.get("original_name", "")
        if not isinstance(original, str) or not original or any(c in original for c in "/\\\x00"):
            raise ValidationError("附件原始名称无效。")
        digest = item.get("sha256", "")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValidationError("附件校验值无效。")
        status = item.get("extraction_status", "")
        if status not in STATUSES:
            raise ValidationError("附件文字提取状态无效。")
        result.append({"stored_name": stored, "original_name": original, "sha256": digest,
                       "extraction_status": status,
                       "extraction_note": str(item.get("extraction_note", ""))[:2000]})
    return result


def extract_docx(path):
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > MAX_FILE_BYTES:
            raise ValidationError("DOCX 解压后的正文过大，请拆分文件。")
        root = ET.fromstring(archive.read(info))
    paragraphs = []
    for paragraph in root.iter(W + "p"):
        parts = []
        for element in paragraph.iter():
            if element.tag == W + "t":
                parts.append(element.text or "")
            elif element.tag == W + "tab":
                parts.append("\t")
            elif element.tag in (W + "br", W + "cr"):
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def extract_pdf(path):
    try:
        pdf = optional_module("pypdf")
    except ImportError:
        return "", "unavailable", "未安装 pypdf，暂时只能保存原件；按 README 安装依赖后重新导入。"
    with open(path, "rb") as stream:
        reader = pdf.PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            return "", "error", "PDF 有密码保护，请手动解除保护后重新导入；原件仍可保存。"
        if len(reader.pages) > 200:
            return "", "error", "PDF 超过 200 页，请先拆分；本次只保留原件。"
        parts = []
        missing = 0
        for page in reader.pages:
            content = page.get_contents()
            if content is not None and len(content.get_data()) > MAX_FILE_BYTES:
                raise ValidationError("PDF 单页内容流过大，请先拆分。")
            text = page.extract_text() or ""
            if not text.strip():
                missing += 1
            parts.append(text)
            if sum(map(len, parts)) > MAX_TEXT_CHARS:
                raise ValidationError("提取文字过长，请拆分文件。")
    text = "\n\n".join(parts)
    if not text.strip():
        return "", "needs_ocr", "未提取到可用文字，可能是扫描/图片型、空白或特殊编码 PDF。需要本地 OCR 或手动输入；原件已保留。"
    if missing:
        return text, "partial", f"有 {missing} 页未提取到文字，可能是扫描页或空白页；请核对原件，必要时做 OCR。"
    return text, "ok", "PDF 文字已提取。图片内文字、表格布局和公式可能不完整，请核对原件。"


def extract_doc(path):
    if sys.platform != "win32":
        return "", "unavailable", "旧 DOC 提取需要 Windows 本地 Word 和 pywin32；可先另存为 DOCX。"
    try:
        optional_module("win32com.client")
    except ImportError:
        return "", "unavailable", "未安装 pywin32，旧 DOC 可保存原件；建议先另存为 DOCX。"
    worker = Path(__file__).with_name("doc_reader.py")
    try:
        response = subprocess.run(
            [sys.executable, "-B", str(worker), str(path.resolve())],
            capture_output=True, text=True, encoding="utf-8", timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return "", "error", "本地 Word 读取超时，已保留原件。请手动另存为 DOCX 后导入。"
    try:
        data = json.loads(response.stdout)
    except (ValueError, TypeError):
        return "", "error", "本地 Word 读取失败，已保留原件。请先另存为 DOCX。"
    if response.returncode or "error" in data:
        return "", "error", data.get("error", "本地 Word 无法读取 DOC。")
    return data["text"], "ok", "通过本地 Word 只读提取；原文件没有被修改。图片、表格及排版请查看原件。"


def extract_text(path):
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            result = extract_pdf(path)
        elif suffix == ".doc":
            result = extract_doc(path)
        elif suffix == ".docx":
            result = (extract_docx(path), "ok", "DOCX 正文和表格中的文字已提取。自动编号、图片、公式及排版请核对原件。")
        else:
            raw = path.read_bytes()
            text = None
            for encoding in ("utf-8-sig", "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8", "gb18030"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeError:
                    continue
            if text is None:
                raise ValidationError("无法识别文本编码。")
            result = (text, "ok", "纯文本已读取。")
        text, status, note = result
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > MAX_TEXT_CHARS:
            return "", "error", "提取文字超过 200 万字符，请拆分文件；原件可保留。"
        if status == "ok" and not text.strip():
            return "", "empty", "文件没有可用正文文字；原件可保留，正文请手动填写。"
        return text, status, note
    except Exception:
        return "", "error", "文字提取失败，文件可能损坏、格式不符或内容过大。可仅保存原件，不会覆盖现有正文。"


class ProtocolFileService:
    def __init__(self, database):
        self.database = database
        self.base = Path(database.db_path).resolve().parent / "data"
        self.storage = self.base / "protocol_files"
        self.staging = self.base / ".protocol_staging"
        self.owned_names = set()

    def stage_import(self, source):
        source = Path(source).resolve()
        if source.suffix.lower() not in EXTENSIONS or not source.is_file():
            raise ValidationError("请选择 DOCX、DOC、PDF、TXT 或 Markdown 文件。")
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValidationError("文件超过 20 MB，请先压缩或拆分。")
        self.staging.mkdir(parents=True, exist_ok=True)
        name = uuid.uuid4().hex + source.suffix.lower()
        target = self.staging / name
        try:
            shutil.copyfile(source, target)
            if target.stat().st_size > MAX_FILE_BYTES:
                raise ValidationError("文件超过 20 MB。")
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        self.owned_names.add(name)
        text, status, note = extract_text(target)
        metadata = {"original_name": source.name, "stored_name": name, "sha256": digest,
                    "extraction_status": status, "extraction_note": note}
        return {"file": metadata, "text": text}

    def path_for(self, metadata):
        metadata = validate_file_metadata([metadata])[0]
        for directory in (self.storage, self.staging):
            path = directory / metadata["stored_name"]
            if path.is_file():
                return path
        raise ValidationError("本地附件副本不存在，请从备份恢复或重新导入。")

    def promote(self, files):
        files = validate_file_metadata(files)
        if files:
            self.storage.mkdir(parents=True, exist_ok=True)
        for item in files:
            path = self.path_for(item)
            if path.parent == self.staging:
                path.replace(self.storage / item["stored_name"])
        return files

    def cleanup_uncommitted(self, names=None):
        if not self.owned_names:
            return
        referenced = self.database.referenced_protocol_files()
        for name in list(self.owned_names if names is None else set(names) & self.owned_names):
            if name not in referenced:
                for directory in (self.staging, self.storage):
                    (directory / name).unlink(missing_ok=True)
            self.owned_names.discard(name)

    def open_file(self, metadata):
        if sys.platform != "win32":
            raise ValidationError("请在文件管理器中打开本地副本：" + str(self.path_for(metadata)))
        os.startfile(str(self.path_for(metadata)))
