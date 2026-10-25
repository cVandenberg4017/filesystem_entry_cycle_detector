import os
import stat
import tempfile
import unittest
from pathlib import Path

from filesystem_entry_cycle_detector import Cycle, CycleDetector, Visit


class TestCycleDetector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _make_dir(self, *parts):
        p = self.root.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def test_no_cycle_flat_tree(self):
        self._make_dir("a")
        (self.root / "a" / "f.txt").write_text("x")
        d = CycleDetector()
        results = list(d.walk(self.root))
        self.assertEqual(len(results), 2)
        self.assertEqual(d.cycles(), [])

    def test_no_cycle_nested(self):
        self._make_dir("a", "b", "c")
        d = CycleDetector()
        results = list(d.walk(self.root))
        self.assertEqual(len(results), 4)
        self.assertEqual(d.cycles(), [])

    def test_symlink_self_cycle_detected(self):
        a = self._make_dir("a")
        link = a / "loop"
        os.symlink(a, link)
        d = CycleDetector()
        list(d.walk(self.root))
        cycles = d.cycles()
        self.assertEqual(len(cycles), 1)
        c = cycles[0]
        self.assertEqual(c.kind, "symlink")
        self.assertGreaterEqual(len(c.entries), 2)
        self.assertEqual(c.entries[-1].path, link)

    def test_symlink_cycle_terminates(self):
        a = self._make_dir("a")
        b = self._make_dir("a", "b")
        os.symlink(a, b / "back")
        d = CycleDetector()
        results = list(d.walk(self.root))
        self.assertGreater(len(results), 0)
        cycles = d.cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].kind, "symlink")

    def test_no_follow_symlinks_no_cycle(self):
        a = self._make_dir("a")
        os.symlink(a, a / "loop")
        d = CycleDetector(follow_symlinks=False)
        list(d.walk(self.root))
        self.assertEqual(d.cycles(), [])

    def test_no_follow_symlinks_hardlink_cycle(self):
        a = self._make_dir("a")
        b = self._make_dir("b")
        try:
            os.link(a, self.root / "a_hard")
        except OSError:
            self.skipTest("hardlinks not supported on this filesystem")
        d = CycleDetector(follow_symlinks=False)
        list(d.walk(self.root))
        cycles = d.cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].kind, "hardlink")

    def test_unreadable_directory_skipped(self):
        a = self._make_dir("a")
        secret = self._make_dir("a", "secret")
        try:
            os.chmod(secret, 0o000)
            d = CycleDetector()
            results = list(d.walk(self.root))
            self.assertIn(self.root, [r[0] for r in results])
            self.assertIn(a, [r[0] for r in results])
        finally:
            os.chmod(secret, 0o755)

    def test_cycle_entries_are_visit_objects(self):
        a = self._make_dir("a")
        os.symlink(a, a / "loop")
        d = CycleDetector()
        list(d.walk(self.root))
        c = d.cycles()[0]
        for v in c.entries:
            self.assertIsInstance(v, Visit)
            self.assertTrue(v.path.is_absolute() or str(v.path).startswith(str(self.root)))

    def test_multiple_cycles_all_reported(self):
        a = self._make_dir("a")
        b = self._make_dir("b")
        os.symlink(a, a / "loop_a")
        os.symlink(b, b / "loop_b")
        d = CycleDetector()
        list(d.walk(self.root))
        cycles = d.cycles()
        self.assertEqual(len(cycles), 2)
        self.assertEqual({c.kind for c in cycles}, {"symlink"})

    def test_hardlink_cycle_when_following_symlinks(self):
        a = self._make_dir("a")
        b = self._make_dir("b")
        try:
            os.link(a, self.root / "a_copy")
        except OSError:
            self.skipTest("hardlinks not supported")
        d = CycleDetector(follow_symlinks=True)
        list(d.walk(self.root))
        cycles = d.cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].kind, "hardlink")

    def test_symlink_to_file_not_a_cycle(self):
        self._make_dir("a")
        f = self.root / "a" / "f.txt"
        f.write_text("x")
        os.symlink(f, self.root / "a" / "link.txt")
        d = CycleDetector()
        list(d.walk(self.root))
        self.assertEqual(d.cycles(), [])


if __name__ == "__main__":
    unittest.main()
