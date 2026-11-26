"""Defensive validation for files received by the hosted Streamlit uploader."""

from collections.abc import Sequence
from typing import Any


_MIB = 1024 * 1024


def validate_uploaded_files(
    files: Sequence[Any],
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> str | None:
    """Return a user-safe validation error, or None when all files are within limits.

    Streamlit enforces the per-file transport cap through server.maxUploadSize.
    This second check protects the analysis pipeline from excessive file counts,
    aggregate uploads, empty files, and unexpected objects without reading their
    contents into another in-memory buffer.
    """
    if max_files < 1 or max_file_bytes < 1 or max_total_bytes < 1:
        raise ValueError("Upload limits must be positive.")

    if len(files) > max_files:
        return f"Upload no more than {max_files} files at a time."

    total_bytes = 0
    max_file_mb = max_file_bytes // _MIB
    max_total_mb = max_total_bytes // _MIB

    for uploaded_file in files:
        size = getattr(uploaded_file, "size", None)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            return (
                "Could not verify an uploaded file size. "
                "Please re-upload your files."
            )

        if size == 0:
            return "Empty files are not accepted."

        if size > max_file_bytes:
            return f"Each file must be {max_file_mb} MB or smaller."

        total_bytes += size
        if total_bytes > max_total_bytes:
            return f"Combined uploads must be {max_total_mb} MB or smaller."

    return None
