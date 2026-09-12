"""Release URLs must follow changed bytes through the complete browser chain."""
import contextlib
import hashlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('cache_stamping', Path(__file__).resolve().parents[1] / 'tools/stamp_cache_tags.py')
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class CacheStampingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        files = {
            'web/index.html': '<script src="public-runtime.js?v=old"></script><script src="app.js?v=old"></script><script src="study.js?v=old"></script>',
            'web/public-runtime.js': "new Worker('engine-worker.mjs?v=old')",
            'web/engine-worker.mjs': "fetch('engine.zip?v=old')",
            'web/engine.zip': 'engine version one',
            'web/app.js': "const room='patient3d/index.html?v=old'",
            'web/patient3d/index.html': '<script src="room.js?v=old"></script>',
            'web/patient3d/room.js': 'renderer version one',
            'web/study.js': "import('./walkthrough-print.js?v=old')",
            'web/walkthrough-print.js': 'print version one',
        }
        for name, data in files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)

    def stamp(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return cache.stamp_tree(self.root, check=check)

    def test_one_pass_updates_worker_iframe_and_print_dependencies(self):
        self.assertEqual(self.stamp(), 0)
        first = (self.root / 'web/index.html').read_bytes()
        for name in ['engine.zip', 'patient3d/room.js', 'walkthrough-print.js']:
            p = self.root / 'web' / name
            p.write_text('version two ' + name)
        self.assertEqual(self.stamp(), 0)
        self.assertNotEqual((self.root / 'web/index.html').read_bytes(), first)
        self.assertEqual(self.stamp(check=True), 0)
        for page, child in [('engine-worker.mjs', 'engine.zip'), ('public-runtime.js', 'engine-worker.mjs'), ('index.html', 'public-runtime.js')]:
            digest = hashlib.sha256((self.root / 'web' / child).read_bytes()).hexdigest()[:10]
            self.assertIn(child + '?v=' + digest, (self.root / 'web' / page).read_text())

    def test_stale_check_is_read_only(self):
        p = self.root / 'web/index.html'
        before = p.read_bytes()
        self.assertEqual(self.stamp(check=True), 1)
        self.assertEqual(p.read_bytes(), before)

    def test_missing_dependency_prevents_partial_writes(self):
        p = self.root / 'web/index.html'
        before = p.read_bytes()
        (self.root / 'web/engine.zip').unlink()
        self.assertEqual(self.stamp(), 1)
        self.assertEqual(p.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
