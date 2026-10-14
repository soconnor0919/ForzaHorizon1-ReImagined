import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from forza_launcher import mods
from forza_launcher.config import Config


class ModTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cfg = Config(self.root / "launcher.json")
        self.cfg.advanced["data_root"] = str(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def add_mod(self, name="sample", **changes):
        folder = self.root / "mods" / name
        folder.mkdir(parents=True)
        manifest = {
            "schema": 1,
            "id": name,
            "name": "Sample mod",
            "environment": {"SAMPLE_PATH": "{mod_dir}"},
            "options": [{
                "key": "quality",
                "label": "Quality",
                "type": "choice",
                "default": "native",
                "choices": [
                    {"value": "native", "label": "Native"},
                    {"value": "fast", "label": "Fast"},
                ],
                "values": {"native": "0", "fast": "1"},
                "ini": {"file": "sample.ini", "section": "Sample", "key": "Quality"},
            }],
        }
        manifest.update(changes)
        (folder / "mod.json").write_text(json.dumps(manifest), encoding="utf-8")
        return folder

    def test_discovers_applies_and_persists_mod_settings(self):
        folder = self.add_mod()
        found, warnings = mods.discover(self.cfg)
        self.assertEqual(warnings, [])
        self.assertEqual([mod.id for mod in found], ["sample"])
        mod = found[0]
        mods.set_enabled(self.cfg, mod, True)
        mods.set_option(self.cfg, mod, mod.options[0], "fast")

        environment, notes = {}, []
        mods.apply(self.cfg, environment, notes)
        self.assertEqual(environment["SAMPLE_PATH"], str(folder.resolve()))
        self.assertIn("Loaded mod: Sample mod.", notes)
        self.assertIn("Quality=1", (folder / "sample.ini").read_text(encoding="utf-8"))

        self.cfg.save()
        loaded = Config(self.cfg.path)
        self.assertTrue(mods.enabled(loaded, mod))
        self.assertEqual(mods.option_value(loaded, mod, mod.options[0]), "fast")

    def test_disabled_mod_does_not_change_environment(self):
        self.add_mod()
        environment, notes = {}, []
        mods.apply(self.cfg, environment, notes)
        self.assertEqual(environment, {})
        self.assertEqual(notes, [])

    def test_requirement_skips_mod_with_a_note(self):
        self.add_mod(requires={"settings": {"gpu_backend": "not-the-active-backend"}})
        mod = mods.discover(self.cfg)[0][0]
        mods.set_enabled(self.cfg, mod, True)
        environment, notes = {}, []
        mods.apply(self.cfg, environment, notes)
        self.assertEqual(environment, {})
        self.assertIn("The mod was skipped.", notes[0])

    def test_invalid_manifest_is_reported_without_hiding_valid_mods(self):
        self.add_mod()
        bad = self.root / "mods" / "bad"
        bad.mkdir(parents=True)
        (bad / "mod.json").write_text('{"schema": 2, "id": "bad"}', encoding="utf-8")
        found, warnings = mods.discover(self.cfg)
        self.assertEqual([mod.id for mod in found], ["sample"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("unsupported manifest schema", warnings[0])

    def test_unknown_environment_placeholder_has_a_friendly_error(self):
        self.add_mod(environment={"BROKEN": "{unknown}"})
        mod = mods.discover(self.cfg)[0][0]
        mods.set_enabled(self.cfg, mod, True)
        with self.assertRaisesRegex(RuntimeError, "invalid environment value"):
            mods.apply(self.cfg, {}, [])

    def test_installs_folder_and_enables_mod(self):
        source = self.root / "download" / "sample-release"
        source.mkdir(parents=True)
        (source / "mod.json").write_text(json.dumps({
            "schema": 1, "id": "folder-mod", "name": "Folder mod"
        }), encoding="utf-8")
        (source / "payload.dll").write_bytes(b"mod")
        mod, replaced = mods.install(self.cfg, source)
        self.assertFalse(replaced)
        self.assertEqual(mod.id, "folder-mod")
        self.assertEqual((self.root / "mods" / "folder-mod" / "payload.dll").read_bytes(), b"mod")
        self.assertTrue(mods.enabled(self.cfg, mod))

    def test_installs_github_style_zip_and_replaces_only_when_requested(self):
        archive = self.root / "sample.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("sample-main/mod.json", json.dumps({
                "schema": 1, "id": "zip-mod", "name": "ZIP mod"
            }))
            z.writestr("sample-main/value.txt", "first")
        mods.install(self.cfg, archive)
        with self.assertRaises(FileExistsError):
            mods.install(self.cfg, archive)

        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("sample-main/mod.json", json.dumps({
                "schema": 1, "id": "zip-mod", "name": "ZIP mod"
            }))
            z.writestr("sample-main/value.txt", "second")
        _mod, replaced = mods.install(self.cfg, archive, replace=True)
        self.assertTrue(replaced)
        self.assertEqual((self.root / "mods" / "zip-mod" / "value.txt").read_text(), "second")

    def test_rejects_zip_path_traversal(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../outside.txt", "no")
            z.writestr("mod.json", json.dumps({"schema": 1, "id": "unsafe"}))
        with self.assertRaisesRegex(mods.InstallError, "unsafe path"):
            mods.install(self.cfg, archive)
        self.assertFalse((self.root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
