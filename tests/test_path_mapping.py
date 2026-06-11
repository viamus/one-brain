from __future__ import annotations

from onebrain_core.path_mapping import resolve_mapped_path


def test_resolve_mapped_windows_path_to_container_path() -> None:
    assert (
        resolve_mapped_path(
            r"C:\DoxieOS\github-private-catalog\libraries",
            r"C:\DoxieOS=/mnt/doxie",
        )
        == "/mnt/doxie/github-private-catalog/libraries"
    )


def test_resolve_mapped_path_leaves_unmatched_path_unchanged() -> None:
    assert resolve_mapped_path(r"D:\Other\file.md", r"C:\DoxieOS=/mnt/doxie") == r"D:\Other\file.md"
