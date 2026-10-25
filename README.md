# filesystem_entry_cycle_detector

Walks a directory tree while tracking visited (device, inode) pairs to detect and report symlink or hardlink cycles that would otherwise silently truncate a walk.

## Usage

```python
from filesystem_entry_cycle_detector import CycleDetector

detector = CycleDetector()
for dirpath, dirnames, filenames in detector.walk("/some/path"):
    print(dirpath, dirnames, filenames)

for cycle in detector.cycles():
    print(cycle.kind, [v.path for v in cycle.entries])
```

## Why

`os.walk` with `followlinks=False` avoids infinite loops by never descending into symlinked directories, but it does so silently: you never learn a loop existed. With `followlinks=True` it will hang or blow the stack on a cycle. This library gives you a third option: follow symlinks, detect the cycle, skip the re-entry, and report what was found.

The detector keys directories by `(st_dev, st_ino)`. A cycle is recorded when a directory already in the visited set is about to be entered again through a link. Re-encountering the same inode through ordinary subdirectory traversal is not treated as a cycle because that path cannot cause infinite recursion on its own.

## Edge cases

On filesystems where hardlinks to directories are not permitted (most Linux ext4 configurations), only symlink cycles can occur. Directory hardlinks are reported as `kind="hardlink"` when the same inode appears on two directory paths reached by normal traversal. Tests that need hardlink support skip themselves when the filesystem refuses to create one.

If `follow_symlinks=False` is passed, symlink targets are never descended into, so only hardlink cycles can be reported.

## Exports

- `CycleDetector(follow_symlinks=True)` — construct a detector; `walk(root)` yields `(dirpath, dirnames, filenames)` triples; `cycles()` returns a list of `Cycle` objects.
- `Cycle` — frozen dataclass with `entries` (tuple of `Visit`) and `kind` (`"symlink"` or `"hardlink"`).
- `Visit` — frozen dataclass with `path` (`pathlib.Path`) and `stat_result` (`os.stat_result`).
