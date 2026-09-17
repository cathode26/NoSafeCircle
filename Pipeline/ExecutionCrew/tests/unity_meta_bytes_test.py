"""P34: crew-staged texture sidecars must import as an ordinary Texture2D, not a
GUID-only stub that Unity 6000.1 defaults to Cube/point-cookie and never rewrites."""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.run_crew import unity_meta_bytes, unity_meta_guid  # noqa: E402

WIZARD_FRAME_PATH = (
    "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/"
    "selected/walk/north/frame_000.png"
)
WIZARD_FRAME_GUID = "e643b744a35ec73f7f8861db43aa1baa"

TEXTURE_EXTENSIONS = ("png", "jpg", "jpeg", "tga", "psd", "gif", "bmp", "tif", "tiff")


class UnityMetaBytesTextureTests(unittest.TestCase):
    def test_new_texture_meta_is_a_default_texture_importer_meta(self):
        data = unity_meta_bytes(WIZARD_FRAME_PATH)
        text = data.decode("ascii")
        self.assertIn("TextureImporter:", text)
        self.assertIn("textureShape: 1", text)
        self.assertIn("cookieLightType: 0", text)
        self.assertIn("applyGammaDecoding: 0", text)
        self.assertIn(f"guid: {WIZARD_FRAME_GUID}\n", text)
        data.decode("ascii")  # re-assert pure ASCII
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))
        for line in text.split("\n"):
            self.assertEqual(line, line.rstrip(), f"trailing whitespace on line: {line!r}")

    def test_extension_matching_is_case_insensitive_for_ldr_textures(self):
        for extension in TEXTURE_EXTENSIONS:
            for candidate in (extension, extension.upper(), extension.capitalize()):
                path = f"Assets/A/B/frame.{candidate}"
                text = unity_meta_bytes(path).decode("ascii")
                self.assertIn("TextureImporter:", text, candidate)
                self.assertIn("textureShape: 1", text, candidate)

    def test_non_texture_paths_are_unchanged_stub_metas(self):
        for extension in ("cs", "unity", "asset", "exr", "hdr"):
            path = f"Assets/A/B.{extension}"
            guid = unity_meta_guid(path)
            expected = f"fileFormatVersion: 2\nguid: {guid}\n".encode("ascii")
            self.assertEqual(unity_meta_bytes(path), expected, extension)

    def test_unity_meta_guid_matches_the_guid_line_for_both_kinds(self):
        for path in (WIZARD_FRAME_PATH, "Assets/A/B.cs"):
            guid = unity_meta_guid(path)
            self.assertRegex(guid, r"^[0-9a-f]{32}$")
            data = unity_meta_bytes(path).decode("ascii")
            self.assertIn(f"guid: {guid}\n", data)

    def test_wizard_frame_guid_is_stable(self):
        self.assertEqual(unity_meta_guid(WIZARD_FRAME_PATH), WIZARD_FRAME_GUID)


if __name__ == "__main__":
    unittest.main()
