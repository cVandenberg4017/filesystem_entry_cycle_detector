from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Iterator, List, Tuple

__all__ = ["Cycle", "CycleDetector", "Visit"]


def _inode_key(st: os.stat_result) -> Tuple[Tuple[int, int], int]:
    """Build a (device, inode) key plus the path's own inode number.

    The path's own inode is reported separately so a caller can distinguish
    a hardlink loop (same inode reachable by two paths) from the ordinary
    case of a directory simply containing an entry that happens to share
    an inode with itself (which never causes a walk to revisit it).
    """
    return (st.st_dev, st.st_ino), st.st_ino


@dataclasses.dataclass(frozen=True)
class Visit:
    """A single directory visited during the walk, with its stat metadata.

    Exposed so callers can build their own reports or pause/resume a walk.
    """
    path: Path
    stat_result: os.stat_result


@dataclasses.dataclass(frozen=True)
class Cycle:
    """A cycle detected during the walk.

    `entries` is the sequence of directory Visits from the first occurrence
    of the inode to the second (inclusive). `kind` is 'symlink' when the
    repeated entry was reached through a symbolic link and 'hardlink'
    otherwise.
    """
    entries: Tuple[Visit, ...]
    kind: str


class CycleDetector:
    """Walk a directory tree, detecting inode cycles caused by links.

    The detector keys visited directories by (st_dev, st_ino). A cycle is
    reported when a directory whose (dev, inode) pair has already been
    entered is about to be entered again via a link. Ordinary re-encounter
    of the same inode through normal subdirectory traversal is not treated
    as a cycle because `os.walk` already prevents infinite recursion there
    via `followlinks=False`. We only surface the link-induced case, which
    is the one `os.walk` silently skips.
    """

    def __init__(self, follow_symlinks: bool = True) -> None:
        # When follow_symlinks is False, symlinks are never descended into,
        # so only hardlink cycles (same inode on two directory paths) can be
        # reported.
        self.follow_symlinks = follow_symlinks
        self._visited: dict = {}
        self._stack: List[Visit] = []
        self._cycles: List[Cycle] = []

    def walk(self, root: os.PathLike) -> Iterator[Tuple[Path, List[str], List[str]]]:
        """Yield (dirpath, dirnames, filenames) like `os.walk`.

        `dirnames` has cycle-causing entries removed so the walk terminates.
        Call `cycles()` afterwards for the list of detected cycles.
        """
        root_path = Path(root)
        yield from self._walk(root_path, via_symlink=False)

    def _walk(
        self, directory: Path, via_symlink: bool
    ) -> Iterator[Tuple[Path, List[str], List[str]]]:
        try:
            st = directory.stat()
        except OSError:
            return

        visit = Visit(path=directory, stat_result=st)
        key, _inode = _inode_key(st)

        if key in self._visited:
            if via_symlink:
                first = self._visited[key]
                start = self._stack.index(first) if first in self._stack else 0
                cycle_visits = [first] + list(self._stack[start:]) + [visit]
                self._cycles.append(Cycle(entries=tuple(cycle_visits), kind="symlink"))
            else:
                self._cycles.append(
                    Cycle(entries=(self._visited[key], visit), kind="hardlink")
                )
            return

        self._visited[key] = visit
        self._stack.append(visit)
        try:
            try:
                entries = sorted(os.listdir(directory))
            except OSError:
                entries = []
            dirnames: List[str] = []
            filenames: List[str] = []
            for name in entries:
                full = directory / name
                try:
                    is_dir = full.is_dir()
                except OSError:
                    is_dir = False
                if is_dir:
                    dirnames.append(name)
                else:
                    filenames.append(name)
            yield (directory, dirnames, filenames)
            for name in dirnames:
                full = directory / name
                try:
                    is_link = full.is_symlink()
                except OSError:
                    is_link = False
                if is_link and not self.follow_symlinks:
                    continue
                yield from self._walk(full, via_symlink=is_link)
        finally:
            self._stack.pop()

    def cycles(self) -> List[Cycle]:
        """Return the cycles detected so far, in detection order."""
        return list(self._cycles)
