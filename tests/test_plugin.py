"""Exercise the built DLL through the public ABI, without a game or GPU."""
import ctypes as c
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOG = c.CFUNCTYPE(None, c.c_char_p)

class Host(c.Structure):
    _fields_ = [("size", c.c_uint32), ("abi", c.c_uint32), ("capabilities", c.c_uint32),
                ("reserved", c.c_uint32), ("log", LOG)]

class Frame(c.Structure):
    _fields_ = [("size", c.c_uint32), ("width", c.c_uint32), ("height", c.c_uint32),
                ("reserved", c.c_uint32), ("number", c.c_uint64)]

class Presentation(c.Structure):
    _fields_ = [("size", c.c_uint32), ("flags", c.c_uint32), ("letterbox", c.c_uint32),
                ("hud_scale", c.c_float)]

class Projection(c.Structure):
    _fields_ = [("size", c.c_uint32), ("view", c.c_uint32), ("width", c.c_uint32),
                ("height", c.c_uint32), ("aspect", c.c_double)]

FRAME = c.CFUNCTYPE(None, c.POINTER(Frame), c.POINTER(Presentation))
PROJECT = c.CFUNCTYPE(None, c.POINTER(Projection))

class Mod(c.Structure):
    _fields_ = [("size", c.c_uint32), ("abi", c.c_uint32), ("name", c.c_char_p),
                ("frame", FRAME), ("project", PROJECT)]

class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = c.CDLL(str(ROOT / "build/ultrawide.dll"))
        cls.initialize = cls.library.ForzaModInit
        cls.initialize.argtypes = [c.POINTER(Host), c.c_char_p]
        cls.initialize.restype = c.POINTER(Mod)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.messages = []
        self.log = LOG(lambda text: self.messages.append(text.decode()))
        self.host = Host(c.sizeof(Host), 1, 1, 0, self.log)
        self.mod = self.initialize(c.byref(self.host), self.directory.name.encode()).contents

    def frame(self, number, width=3440, height=1440):
        frame = Frame(c.sizeof(Frame), width, height, 0, number)
        result = Presentation(c.sizeof(Presentation), 0, 1, 1)
        self.mod.frame(c.byref(frame), c.byref(result))
        return result

    def projection(self, view=1, width=1280, height=720):
        event = Projection(c.sizeof(Projection), view, width, height, 16 / 9)
        self.mod.project(c.byref(event))
        return event.aspect

    def gameplay(self, width, height):
        self.frame(1, width, height)
        self.projection()
        return self.frame(2, width, height)

    def test_21_9_camera_and_hud(self):
        result = self.gameplay(3440, 1440)
        self.assertFalse(result.letterbox)
        self.assertAlmostEqual(self.projection(), 3440 / 1440)
        self.assertAlmostEqual(result.hud_scale, (3440 / 1440) / (16 / 9), places=5)

    def test_32_9_camera_and_hud(self):
        result = self.gameplay(5120, 1440)
        self.assertAlmostEqual(self.projection(), 32 / 9)
        self.assertEqual(result.hud_scale, 2)

    def test_16_9_is_unchanged(self):
        result = self.gameplay(2560, 1440)
        self.assertTrue(result.letterbox)
        self.assertEqual(result.hud_scale, 1)
        self.assertAlmostEqual(self.projection(), 16 / 9)

    def test_narrow_window_and_minimized_window(self):
        for width, height in ((1280, 1024), (0, 0)):
            result = self.gameplay(width, height)
            self.assertTrue(result.letterbox)
            self.assertEqual(result.hud_scale, 1)

    def test_map_and_thumbnails_keep_original_projection(self):
        self.gameplay(3440, 1440)
        self.assertAlmostEqual(self.projection(2), 16 / 9)
        self.assertAlmostEqual(self.projection(1, 256, 256), 16 / 9)
        self.assertAlmostEqual(self.projection(0, 640, 360), 16 / 9)

    def test_culling_uses_the_same_aspect_as_the_camera(self):
        self.gameplay(3440, 1440)
        self.assertAlmostEqual(self.projection(0), self.projection(1))

    def test_map_returns_to_protected_framing(self):
        self.gameplay(3440, 1440)
        for number in range(3, 8):
            self.projection(2)
            result = self.frame(number)
        self.assertTrue(result.letterbox)
        self.assertEqual(result.hud_scale, 1)

    def test_menu_after_gameplay_returns_to_protected_framing(self):
        self.gameplay(3440, 1440)
        result = self.frame(34)
        self.assertTrue(result.letterbox)
        self.assertEqual(result.hud_scale, 1)

    def test_hud_setting_reaches_the_plugin(self):
        Path(self.directory.name, "ultrawide.ini").write_text("[Ultrawide]\nCenterHud=0\n")
        self.mod = self.initialize(c.byref(self.host), self.directory.name.encode()).contents
        self.assertEqual(self.gameplay(5120, 1440).hud_scale, 1)
        self.assertAlmostEqual(self.projection(), 32 / 9)

    def test_missing_graphics_capability_rejects_mod(self):
        self.host.capabilities = 0
        self.assertFalse(self.initialize(c.byref(self.host), self.directory.name.encode()))

    def test_incompatible_abi_rejects_mod(self):
        self.host.abi = 999
        self.assertFalse(self.initialize(c.byref(self.host), self.directory.name.encode()))

if __name__ == "__main__":
    unittest.main()
