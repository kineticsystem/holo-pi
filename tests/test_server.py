"""Tests the HTTP server, with a fake screen: skipped without FastAPI, httpx and python-multipart."""

import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

try:
    from fastapi.testclient import TestClient

    from stepit_holo.server import Display, create_app
except ImportError as error:  # The server's packages are optional.
    raise unittest.SkipTest(f"no server packages: {error}")

from test_stepit_holo import VISUAL, numbered_quilt


class FakeScreen:
    """A screen of 1536 x 2048 that keeps what it is shown, or is switched off."""

    name = "fake"

    def __init__(self):
        self.shown = None
        self.on = True
        self.cleared = threading.Event()

    def show(self, hologram):
        if not self.on:
            raise RuntimeError("no screen of 1536 x 2048")
        self.shown = hologram
        return "the fake screen"

    def clear(self):
        self.shown = None
        self.cleared.set()


def png(quilt):
    buffer = io.BytesIO()
    Image.fromarray(quilt).save(buffer, "PNG")
    return buffer.getvalue()


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = Path(self.folder.name)
        self.screen = FakeScreen()
        self.display = Display(self.screen, calibration=VISUAL, state=self.state, mount=False)
        self.client = TestClient(create_app(self.display))
        self.quilt = png(numbered_quilt())

    def tearDown(self):
        self.folder.cleanup()

    def upload(self, name="test_qs8x6a0.75.png", data=None, **fields):
        return self.client.post("/quilt", files={"file": (name, data or self.quilt, "image/png")},
                                data={key: str(value) for key, value in fields.items()})

    def test_shows_an_uploaded_quilt(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        quilt = response.json()
        self.assertEqual((quilt["columns"], quilt["rows"], quilt["shown"]), (8, 6, True))
        self.assertEqual(quilt["shown_on"], "the fake screen")
        self.assertEqual(self.screen.shown.shape, (2048, 1536, 3))
        # Every view of the numbered quilt is seen: it was interleaved.
        self.assertEqual(list(np.unique(self.screen.shown)), list(range(1, 49)))

    def test_takes_the_layout_from_the_fields(self):
        response = self.upload("test.png", columns=8, rows=6, reverse="true")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["reverse"])

    def test_refuses_a_quilt_of_no_layout(self):
        response = self.upload("test.png")
        self.assertEqual(response.status_code, 400)
        self.assertIn("give columns and rows", response.json()["detail"])

    def test_refuses_what_is_not_an_image(self):
        response = self.upload(data=b"not an image")
        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot read the quilt", response.json()["detail"])

    def test_keeps_a_quilt_it_cannot_show_and_shows_it_later(self):
        self.screen.on = False
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn("kept", response.json()["detail"])
        quilt = self.client.get("/status").json()["quilt"]
        self.assertEqual((quilt["shown"], quilt["error"]), (False, "no screen of 1536 x 2048"))
        self.screen.on = True
        self.display.retry()
        self.assertTrue(self.client.get("/status").json()["quilt"]["shown"])

    def test_shows_the_last_quilt_again_after_a_restart(self):
        self.upload()
        screen = FakeScreen()
        display = Display(screen, calibration=VISUAL, state=self.state, mount=False)
        display.restore()
        display.retry()
        self.assertEqual(display.quilt_status()["name"], "test_qs8x6a0.75.png")
        np.testing.assert_array_equal(screen.shown, self.screen.shown)

    def test_gives_the_quilt_back(self):
        self.assertEqual(self.client.get("/quilt").status_code, 404)
        self.upload()
        response = self.client.get("/quilt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.quilt)

    def test_removing_the_quilt_shows_black_and_forgets_it(self):
        self.upload()
        self.assertEqual(self.client.delete("/quilt").status_code, 204)
        self.assertTrue(self.screen.cleared.is_set())
        self.assertIsNone(self.client.get("/status").json()["quilt"])
        self.assertEqual(list(self.state.glob("quilt*")), [])

    def test_shows_the_test_quilt(self):
        response = self.client.post("/numbers")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "numbers")
        self.assertEqual(Image.open(io.BytesIO(self.client.get("/quilt").content)).size, (3360, 3360))

    def test_status_and_calibration(self):
        status = self.client.get("/status").json()
        self.assertEqual(status["screen"], "fake")
        self.assertIsNone(status["quilt"])
        calibration = self.client.get("/calibration").json()
        self.assertEqual((calibration["serial"], calibration["width"]), ("LKG-PORT-00000", 1536))
        self.assertEqual(self.client.get("/status").json()["looking_glass"]["height"], 2048)

    def test_no_calibration_is_unavailable(self):
        display = Display(FakeScreen(), state=self.state, mount=False)
        display._read_calibration = lambda: (_ for _ in ()).throw(RuntimeError("no Looking Glass found"))
        client = TestClient(create_app(display))
        self.assertEqual(client.get("/calibration").status_code, 503)
        self.assertIn("no Looking Glass found", client.get("/status").json()["calibration_error"])

    def test_mounts_the_drive_only_when_asked(self):
        for mount, calls in [(False, 0), (True, 1)]:
            display = Display(FakeScreen(), state=self.state, mount=mount)
            missing = RuntimeError("no Looking Glass found")
            with mock.patch("stepit_holo.server.find_calibration", side_effect=missing), \
                    mock.patch("stepit_holo.server.mount_drives", return_value=[]) as mount_drives, \
                    self.assertRaisesRegex(RuntimeError, "no Looking Glass found"):
                display.calibration()
            self.assertEqual(mount_drives.call_count, calls)

    def test_documents_every_route(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertEqual(set(paths), {"/status", "/calibration", "/quilt", "/numbers"})
        for methods in paths.values():
            for operation in methods.values():
                self.assertTrue(operation.get("summary") and operation.get("description"))


if __name__ == "__main__":
    unittest.main()
