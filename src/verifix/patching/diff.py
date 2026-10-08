from __future__ import annotations

import re

from verifix.models.patch import ChangedFile, ChangeType

_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.MULTILINE)


def parse_changed_files(diff: str) -> list[ChangedFile]:
    """Split a unified git diff into per-file ChangedFile entries."""
    matches = list(_HEADER.finditer(diff))
    files = []
    for i, m in enumerate(matches):
        chunk = diff[m.start(): matches[i + 1].start() if i + 1 < len(matches) else len(diff)]
        kind = (ChangeType.ADDED if "\nnew file mode" in chunk else
                ChangeType.DELETED if "\ndeleted file mode" in chunk else ChangeType.MODIFIED)
        files.append(ChangedFile(path=m.group(2), change_type=kind, diff=chunk))
    return files


def new_file_diff(path: str, content: str) -> str:
    """A git diff that creates `path` with `content` (so generated tests can ride along in a sandbox run)."""
    lines = content.splitlines()
    body = "".join(f"+{ln}\n" for ln in lines)
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}")
