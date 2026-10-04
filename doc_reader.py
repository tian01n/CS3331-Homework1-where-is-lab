"""独立进程使用本地 Word 只读提取 DOC；不启用宏，不保存源文件。"""

import json
import sys


def read_doc(path):
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = document = None
    previous_update_links = None
    previous_security = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        previous_security = word.AutomationSecurity
        word.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        previous_update_links = word.Options.UpdateLinksAtOpen
        word.Options.UpdateLinksAtOpen = False
        document = word.Documents.Open(
            FileName=path, ReadOnly=True, AddToRecentFiles=False,
            ConfirmConversions=False, Visible=False, NoEncodingDialog=True,
            PasswordDocument="__NO_PASSWORD_PROVIDED__",
        )
        return document.Content.Text.replace("\r", "\n").replace("\x07", "\t")
    finally:
        try:
            if document is not None:
                document.Close(SaveChanges=0)
        finally:
            try:
                if word is not None:
                    try:
                        if previous_update_links is not None:
                            word.Options.UpdateLinksAtOpen = previous_update_links
                        if previous_security is not None:
                            word.AutomationSecurity = previous_security
                    finally:
                        word.Quit(SaveChanges=0)
            finally:
                pythoncom.CoUninitialize()


if __name__ == "__main__":
    try:
        print(json.dumps({"text": read_doc(sys.argv[1])}, ensure_ascii=True))
    except Exception:
        print(json.dumps({"error": "本地 Word 无法读取该 DOC。请手动另存为 DOCX 后重新导入。"},
                         ensure_ascii=True))
        sys.exit(1)
