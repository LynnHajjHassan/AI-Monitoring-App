import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from capture_window import RecentFrames


class RecentFramesTests(unittest.TestCase):
    def test_time_and_count_limits(self):
        buffer = RecentFrames(window_seconds=30, max_frames=2)
        for now in (0, 1, 2):
            buffer.add(now, b'jpeg', {})
        self.assertEqual([frame[0] for frame in buffer.frames], [1, 2])
        buffer.prune(32)
        self.assertEqual([frame[0] for frame in buffer.frames], [2])
        buffer.prune(33)
        self.assertFalse(buffer.frames)

    def test_export_contains_only_recent_evidence(self):
        buffer = RecentFrames()
        metadata = {'request_started_at': 'start', 'received_at': 'end'}
        buffer.add(0, b'old', metadata)
        buffer.add(29, b'recent', metadata)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'evidence'
            buffer.save(directory, 31)
            manifest = json.loads((directory / 'manifest.json').read_text())
            self.assertEqual(manifest['frame_count'], 1)
            self.assertEqual((directory / 'frame-000.jpg').read_bytes(), b'recent')
            with self.assertRaises(ValueError):
                buffer.save(Path(tmp) / 'empty', 60)


if __name__ == '__main__':
    unittest.main()
