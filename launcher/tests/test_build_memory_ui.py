import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from forza_launcher import build_env
from forza_launcher.config import Config
from forza_launcher.ui.pages import SetupPage


class BuildMemoryUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Config(Path(self.temp.name) / "launcher.json")
        self.cfg.advanced["data_root"] = self.temp.name
        self.cfg.advanced["build_jobs"] = 3
        for target, kwargs in [
            ("forza_launcher.build_env.ram_bytes", {"return_value": (8 * build_env.GB, 5 * build_env.GB)}),
            ("forza_launcher.build_env.free_disk", {"return_value": 100 * build_env.GB}),
            ("forza_launcher.build_env.detect_tools", {"return_value": build_env.Tools()}),
        ]:
            mocker = patch(target, **kwargs)
            mocker.start()
            self.addCleanup(mocker.stop)
        with patch.object(SetupPage, "refresh"):
            self.page = SetupPage(self.cfg, None)
        self.addCleanup(self.page.close)
        self.addCleanup(self.page.timer.stop)

    def test_job_spinner_refreshes_estimate_and_saves_selection(self):
        self.page._refresh_checks()
        self.assertIn("2.5 GB for 3 jobs", self.page.checks.itemAt(0).widget().detail.text())
        self.page.jobs.setValue(16)
        row = self.page.checks.itemAt(0).widget()
        self.assertIn("9 GB for 16 jobs", row.detail.text())
        self.assertIn("reduce parallel jobs", row.detail.text())
        saved = json.loads(self.cfg.path.read_text())
        self.assertEqual(saved["advanced"]["build_jobs"], 16)

    def test_low_memory_warning_does_not_prompt_and_build_uses_selected_jobs(self):
        with patch.object(build_env, "ram_bytes", return_value=(8 * build_env.GB, build_env.GB)), \
             patch("forza_launcher.ui.pages.installer.check_game_folder", return_value=(True, "ready")), \
             patch.object(build_env, "usable_vs_installed", return_value=True), \
             patch("forza_launcher.ui.pages.workers.build_task", return_value=MagicMock()) as task, \
             patch.object(self.page, "_start"), \
             patch.object(QMessageBox, "question") as question:
            self.page._build()
            question.assert_not_called()
            self.assertEqual(task.call_args.args[0].jobs, 3)

    def test_disk_error_still_prompts_and_can_cancel_the_build(self):
        with patch.object(build_env, "free_disk", return_value=build_env.GB), \
             patch("forza_launcher.ui.pages.installer.check_game_folder", return_value=(True, "ready")), \
             patch.object(build_env, "usable_vs_installed", return_value=True), \
             patch("forza_launcher.ui.pages.workers.build_task") as task, \
             patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
            self.page._build()
            question.assert_called_once()
            self.assertIn("Disk:", question.call_args.args[2])
            task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
