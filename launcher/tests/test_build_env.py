import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forza_launcher import build_env


class MemoryPreflight(unittest.TestCase):
    def checks(self, total, available, jobs=3, disk=100):
        with patch.object(build_env, "ram_bytes", return_value=(total * build_env.GB, available * build_env.GB)), \
             patch.object(build_env, "free_disk", return_value=disk * build_env.GB), \
             patch.object(build_env.os, "cpu_count", return_value=16):
            return build_env.preflight(Path(tempfile.gettempdir()), True, False, jobs=jobs)

    def test_reported_8gb_machine_with_5gb_free_is_not_blocked(self):
        checks = self.checks(8, 5)
        self.assertEqual(checks[0][0], "ok")
        self.assertIn("2.5 GB for 3 jobs", checks[0][1])
        self.assertFalse(any(level == "error" for level, _ in checks))

    def test_less_than_8gb_installed_can_fit_a_small_build(self):
        self.assertEqual(self.checks(6, 4)[0][0], "ok")

    def test_selected_jobs_change_the_warning(self):
        self.assertEqual(self.checks(8, 5, jobs=3)[0][0], "ok")
        level, text = self.checks(8, 5, jobs=16)[0]
        self.assertEqual(level, "warn")
        self.assertIn("9 GB for 16 jobs", text)
        self.assertIn("reduce parallel jobs", text)

    def test_borderline_or_exhausted_memory_warns_instead_of_errors(self):
        self.assertEqual(self.checks(8, 2.5)[0][0], "warn")
        self.assertEqual(self.checks(8, 0)[0][0], "warn")

    def test_unknown_memory_is_not_a_zero_memory_error(self):
        level, text = self.checks(0, 0)[0]
        self.assertEqual(level, "warn")
        self.assertIn("could not be determined", text)

    def test_low_disk_still_has_its_error(self):
        checks = self.checks(8, 5, disk=1)
        self.assertEqual(checks[0][0], "ok")
        self.assertEqual(checks[1][0], "error")

    def test_automatic_jobs_leave_headroom_and_respect_core_limit(self):
        with patch.object(build_env, "ram_bytes", return_value=(8 * build_env.GB, 5 * build_env.GB)), \
             patch.object(build_env.os, "cpu_count", return_value=16):
            jobs = build_env.default_jobs()
            self.assertGreater(jobs, 1)
            self.assertLessEqual(build_env.build_ram_gb(jobs) * build_env.RAM_HEADROOM, 5)
            self.assertEqual(build_env.preflight(Path(tempfile.gettempdir()), True, False)[0][0], "ok")
        with patch.object(build_env, "ram_bytes", return_value=(64 * build_env.GB, 50 * build_env.GB)), \
             patch.object(build_env.os, "cpu_count", return_value=2):
            self.assertEqual(build_env.default_jobs(), 2)

    def test_automatic_jobs_handle_exhausted_and_unknown_memory(self):
        with patch.object(build_env.os, "cpu_count", return_value=8):
            with patch.object(build_env, "ram_bytes", return_value=(8 * build_env.GB, 0)):
                self.assertEqual(build_env.default_jobs(), 1)
            with patch.object(build_env, "ram_bytes", return_value=(0, 0)):
                self.assertEqual(build_env.default_jobs(), 8)


if __name__ == "__main__":
    unittest.main()
