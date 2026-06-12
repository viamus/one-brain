from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath


def resolve_mapped_path(path: str, mappings: str) -> str:
    """Map host paths to container paths for MCP HTTP file import.

    Mappings use `host=container` pairs separated by semicolons, for example:
    `C:\\DoxieOS=/mnt/doxie;D:\\data=/mnt/data`.
    """

    normalized = path.strip()
    if not normalized or not mappings.strip():
        return normalized

    for raw_pair in mappings.split(";"):
        if "=" not in raw_pair:
            continue
        host_raw, container_raw = raw_pair.split("=", 1)
        host = host_raw.strip().rstrip("\\/")
        container = container_raw.strip().rstrip("/")
        if not host or not container:
            continue
        remainder = _windows_remainder(normalized, host)
        if remainder is None:
            remainder = _posix_remainder(normalized, host)
        if remainder is None:
            continue
        if not remainder:
            return container
        return str(PurePosixPath(container, *remainder))

    return normalized


def _windows_remainder(path: str, prefix: str) -> list[str] | None:
    path_parts = PureWindowsPath(path).parts
    prefix_parts = PureWindowsPath(prefix).parts
    if len(path_parts) < len(prefix_parts):
        return None
    left = [part.casefold() for part in path_parts[: len(prefix_parts)]]
    right = [part.casefold() for part in prefix_parts]
    if left != right:
        return None
    return list(path_parts[len(prefix_parts) :])


def _posix_remainder(path: str, prefix: str) -> list[str] | None:
    path_parts = PurePosixPath(path).parts
    prefix_parts = PurePosixPath(prefix).parts
    if len(path_parts) < len(prefix_parts):
        return None
    if path_parts[: len(prefix_parts)] != prefix_parts:
        return None
    return list(path_parts[len(prefix_parts) :])
