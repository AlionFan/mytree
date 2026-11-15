"""认领冲突、消息并发与错误恢复；全部使用临时目录。"""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "coord.py"
SPEC = importlib.util.spec_from_file_location("hks_coord", SCRIPT)
coord = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coord)


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()

    def tearDown(self):
        self.directory.cleanup()

    def run_command(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = coord.main(list(arguments), root=self.root)
        return result, json.loads(out.getvalue()) if out.getvalue() else err.getvalue()

    def claim(self, task, agent, scope):
        return self.run_command("claim", "--task", task, "--agent", agent, "--scope", scope, "--req", "DEV-002")

    def test_parent_child_and_same_file_conflicts_but_distinct_work_is_allowed(self):
        self.assertEqual(self.claim("front", "claude", "mytree/web")[0], 0)
        self.assertEqual(self.claim("file", "codex", "mytree/web/app.js")[0], 1)
        self.assertEqual(self.claim("parent", "codex", "mytree")[0], 1)
        self.assertEqual(self.claim("backend", "codex", "mytree/app")[0], 0)
        self.assertEqual(self.claim("front", "codex", "android")[0], 1)

    def test_owner_can_repeat_claim_and_released_scope_can_be_handed_off(self):
        self.assertEqual(self.claim("front", "claude", "mytree/web")[0], 0)
        self.assertEqual(self.claim("front", "claude", "mytree/web")[0], 0)
        self.assertEqual(self.run_command("done", "--task", "front", "--agent", "codex", "--summary", "不能代交")[0], 1)
        self.assertEqual(self.run_command("done", "--task", "front", "--agent", "claude", "--summary", "交接")[0], 0)
        self.assertEqual(self.claim("review", "codex", "mytree/web/app.js")[0], 0)

    def test_paths_cannot_escape_root_or_use_globs_including_symlinks(self):
        outside = self.root.parent / "outside-coord-test"
        (self.root / "external").symlink_to(outside, target_is_directory=True)
        for scope in ("../outside", "/tmp/outside", "mytree/*", ".", ".coordination/state.json", "external/code.py"):
            with self.subTest(scope=scope):
                self.assertEqual(self.claim("escape", "codex", scope)[0], 1)

    def test_aliases_and_ack_only_cover_returned_messages(self):
        for target in ("claude", "codex", "all", "claude-web"):
            self.assertEqual(self.run_command("send", "--from", "codex", "--to", target, "--text", target)[0], 0)
        _, first = self.run_command("inbox", "--agent", "claude-web", "--limit", "1")
        self.assertEqual([m["id"] for m in first["messages"]], [1])
        self.assertEqual(first["acked_through"], 0)
        self.run_command("inbox", "--agent", "claude-web", "--limit", "1", "--ack")
        _, remaining = self.run_command("inbox", "--agent", "claude-web")
        self.assertEqual([m["id"] for m in remaining["messages"]], [3, 4])
        _, other = self.run_command("inbox", "--agent", "claude-other")
        self.assertEqual([m["id"] for m in other["messages"]], [1, 3])

    def test_concurrent_messages_do_not_overwrite_each_other(self):
        code = "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from coord import main;sys.exit(main(sys.argv[3:],root=Path(sys.argv[2])))"
        workers = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPT.parent), str(self.root),
                                     "send", "--from", "codex", "--to", "claude", "--text", f"message-{i}"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(8)]
        for worker in workers:
            out, error = worker.communicate(timeout=15)
            self.assertEqual(worker.returncode, 0, error.decode())
        _, inbox = self.run_command("inbox", "--agent", "claude")
        self.assertEqual([m["id"] for m in inbox["messages"]], list(range(1, 9)))
        self.assertEqual(len({m["text"] for m in inbox["messages"]}), 8)

    def test_concurrent_claim_has_only_one_winner(self):
        code = "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from coord import main;sys.exit(main(sys.argv[3:],root=Path(sys.argv[2])))"
        workers = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPT.parent), str(self.root),
                                     "claim", "--agent", actor, "--task", actor, "--scope", "mytree/web/app.js"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for actor in ("codex", "claude")]
        results = []
        for worker in workers:
            worker.communicate(timeout=15)
            results.append(worker.returncode)
        self.assertEqual(sorted(results), [0, 1])

    def test_corrupt_state_is_reported_without_overwriting(self):
        folder = self.root / ".coordination"
        folder.mkdir()
        state = folder / "state.json"
        state.write_text("broken", encoding="utf-8")
        self.assertEqual(self.run_command("send", "--from", "codex", "--to", "claude", "--text", "hi")[0], 1)
        self.assertEqual(state.read_text(), "broken")

    def test_state_permissions_are_private(self):
        self.run_command("send", "--from", "codex", "--to", "claude", "--text", "hi")
        self.assertEqual((self.root / ".coordination/state.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
