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
