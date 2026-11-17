"""Tests the HTTP API, with a fake screen: skipped without FastAPI, httpx and python-multipart. The tests of videos
are skipped without PyAV too."""

import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

try:
    from fastapi.testclient import TestClient

    from holo_pi.server import Display, create_app
except ImportError as error:  # The server's packages are optional.
    raise unittest.SkipTest(f"no server packages: {error}")

from test_holo_pi import VISUAL, numbered_quilt

try:
    from test_video import COLOURS, hologram_video, quilt_video

    from holo_pi.video import NoPyAV
except unittest.SkipTest:  # No PyAV: no videos.
    hologram_video = None


class FakeScreen:
    """A screen of 1536 x 2048 that keeps what it is shown, how many frames, or is switched off."""

    name = "fake"

    def __init__(self):
        self.shown = None
        self.frames = 0
        self.on = True
        self.cleared = threading.Event()

    def show(self, hologram):
        if not self.on:
            raise RuntimeError("no screen of 1536 x 2048")
        self.shown = hologram
        self.frames += 1
        return "the fake screen"

    def clear(self):
        self.shown = None
        self.cleared.set()


class GpuScreen(FakeScreen):
    """A fake screen with a GPU: it keeps what it is asked to interleave."""

    def __init__(self):
        super().__init__()
        self.quilts, self.frames_shown = [], []

    def show_quilt(self, picture, layout, calibration, reverse=False):
        self.quilts.append((picture.shape, (layout.columns, layout.rows), reverse))
        return "the fake GPU"

    def show_quilt_frame(self, frame, layout, calibration, reverse=False):
        self.frames_shown.append((frame.format.name, frame.width, frame.height, (layout.columns, layout.rows)))
        return "the fake GPU"


def png(quilt):
    buffer = io.BytesIO()
    Image.fromarray(quilt).save(buffer, "PNG")
    return buffer.getvalue()


def wait_for(condition, what):
    for _ in range(500):
        if condition():
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"waited in vain for {what}")


class ApiTest(unittest.TestCase):
    """A server on a temporary state folder, a fake screen and a Portrait's calibration."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = Path(self.folder.name)
        self.screen = FakeScreen()
        self.displays = []
        self.display, self.client = self.server(self.screen)
        self.quilt = png(numbered_quilt())

    def tearDown(self):
        for display in self.displays:
            display.stop()
        self.folder.cleanup()

    def server(self, screen, **options):
        options.setdefault("calibration", VISUAL)
        display = Display(screen, state=self.state, mount=False, **options)
        self.displays.append(display)
        return display, TestClient(create_app(display))

    def upload(self, name="test_qs8x6a0.75.png", data=None, client=None, **fields):
        return (client or self.client).post("/api/media", files={"file": (name, data or self.quilt)},
                                            data={key: str(value).lower() for key, value in fields.items()})

    def show(self, client=None, **request):
        return (client or self.client).put("/api/display", json=request)


class MediaTest(ApiTest):
    def test_keeps_a_quilt_without_showing_it(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        self.assertEqual(response.headers["location"], f"/api/media/{item['id']}")
        self.assertEqual((item["name"], item["kind"], item["columns"], item["rows"], item["width"], item["shown"]),
                         ("test_qs8x6a0.75.png", "quilt", 8, 6, 336, False))
        self.assertEqual(item["size"], len(self.quilt))
        self.assertIsNone(self.screen.shown)
        self.assertIsNone(self.client.get("/api/display").json()["source"])

    def test_shows_a_quilt_at_once_with_play(self):
        item = self.upload(play=True).json()
        self.assertTrue(item["shown"])
        self.assertEqual(self.screen.shown.shape, (2048, 1536, 3))
        # Every view of the numbered quilt is seen: it was interleaved.
        self.assertEqual(list(np.unique(self.screen.shown)), list(range(1, 49)))
        display = self.client.get("/api/display").json()
        self.assertEqual((display["source"], display["kind"], display["media"]["id"], display["shown_on"]),
                         ("media", "quilt", item["id"], "the fake screen"))

    def test_takes_the_layout_from_the_fields(self):
        item = self.upload("test.png", columns=8, rows=6, reverse=True).json()
        self.assertEqual((item["columns"], item["reverse"]), (8, True))

    def test_refuses_a_quilt_of_no_layout(self):
        response = self.upload("test.png")
        self.assertEqual(response.status_code, 400)
        self.assertIn("give columns and rows", response.json()["error"])

    def test_needs_both_columns_and_rows(self):
        response = self.upload("test.png", columns=8)
        self.assertEqual(response.status_code, 400)
        self.assertIn("give both columns and rows", response.json()["error"])

    def test_refuses_what_is_neither_an_image_nor_a_video(self):
        response = self.upload(data=b"neither")
        self.assertEqual(response.status_code, 400)
        self.assertIn("as an image or a video", response.json()["error"])
        self.assertEqual(self.client.get("/api/media").json()["items"], [])

    def test_a_field_of_the_wrong_kind_is_an_error_too(self):
        response = self.upload(columns=0, rows=6)
        self.assertEqual(response.status_code, 422)
        self.assertIn("columns", response.json()["error"])

    def test_the_same_name_replaces_and_keeps_the_id(self):
        first = self.upload().json()
        response = self.upload(data=png(numbered_quilt(width=21, height=28)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["id"], response.json()["width"]), (first["id"], 168))
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 1)

    def test_lists_the_media(self):
        self.upload("a_qs8x6a0.75.png")
        self.upload("b_qs8x6a0.75.png")
        media = self.client.get("/api/media").json()
        self.assertEqual([item["name"] for item in media["items"]], ["a_qs8x6a0.75.png", "b_qs8x6a0.75.png"])
        self.assertEqual(media["size"], 2 * len(self.quilt))
        self.assertGreater(media["free"], 0)

    def test_gives_a_medium_and_its_content(self):
        item = self.upload().json()
        self.assertEqual(self.client.get(f"/api/media/{item['id']}").json()["name"], "test_qs8x6a0.75.png")
        response = self.client.get(f"/api/media/{item['id']}/content")
        self.assertEqual((response.status_code, response.content), (200, self.quilt))
        self.assertIn("test_qs8x6a0.75.png", response.headers["content-disposition"])

    def test_an_unknown_id_is_not_found(self):
        for method, path in [("get", "/api/media/nope"), ("get", "/api/media/nope/content"),
                             ("delete", "/api/media/nope")]:
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": "no medium of the id 'nope'"})

    def test_removing_the_medium_shown_shows_black(self):
        item = self.upload(play=True).json()
        self.assertEqual(self.client.delete(f"/api/media/{item['id']}").status_code, 204)
        self.assertTrue(self.screen.cleared.is_set())
        self.assertIsNone(self.client.get("/api/display").json()["source"])
        self.assertEqual(self.client.get("/api/media").json()["items"], [])
        self.assertEqual(list((self.state / "library").glob("*.png")), [])

    def test_removing_another_medium_leaves_the_display(self):
        shown = self.upload("a_qs8x6a0.75.png", play=True).json()
        other = self.upload("b_qs8x6a0.75.png").json()
        self.client.delete(f"/api/media/{other['id']}")
        self.assertEqual(self.client.get("/api/display").json()["media"]["id"], shown["id"])

    def test_removes_every_medium(self):
        self.upload("a_qs8x6a0.75.png", play=True)
        self.upload("b_qs8x6a0.75.png")
        self.assertEqual(self.client.delete("/api/media").status_code, 204)
        self.assertEqual(self.client.get("/api/media").json()["items"], [])
        self.assertTrue(self.screen.cleared.is_set())


class DisplayTest(ApiTest):
    def test_shows_a_medium_by_its_id_or_its_name(self):
        a = self.upload("a_qs8x6a0.75.png").json()
        b = self.upload("b_qs8x6a0.75.png").json()
        response = self.show(media_id=a["id"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["media"]["id"], response.json()["shown"]), (a["id"], True))
        self.assertEqual(self.show(media_name="b_qs8x6a0.75.png").json()["media"]["id"], b["id"])
        media = {item["id"]: item["shown"] for item in self.client.get("/api/media").json()["items"]}
        self.assertEqual(media, {a["id"]: False, b["id"]: True})

    def test_an_unknown_medium_is_not_found(self):
        self.assertEqual(self.show(media_id="nope").status_code, 404)
        response = self.show(media_name="nope.png")
        self.assertEqual(response.status_code, 404)
        self.assertIn("no quilt or video of the name 'nope.png'", response.json()["error"])

    def test_needs_one_thing_to_show(self):
        for request in [{}, {"media_id": "a", "media_name": "b"}, {"media_id": "a", "test_pattern": True}]:
            response = self.show(**request)
            self.assertEqual(response.status_code, 400, request)
            self.assertIn("give one of media_id, media_name and test_pattern", response.json()["error"])

    def test_shows_the_test_pattern(self):
        display = self.show(test_pattern=True, reverse=True).json()
        self.assertEqual((display["source"], display["name"], display["reverse"], display["shown"]),
                         ("test pattern", "numbers", True, True))
        self.assertIsNone(display["media"])

    def test_black_keeps_the_medium_in_the_library(self):
        self.upload(play=True)
        self.assertEqual(self.client.delete("/api/display").status_code, 204)
        self.assertTrue(self.screen.cleared.is_set())
        self.assertIsNone(self.client.get("/api/display").json()["source"])
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 1)

    def test_keeps_what_it_cannot_show_and_shows_it_later(self):
        item = self.upload().json()
        self.screen.on = False
        response = self.show(media_id=item["id"])
        self.assertEqual(response.status_code, 503)
        self.assertIn("kept", response.json()["error"])
        display = self.client.get("/api/display").json()
        self.assertEqual((display["shown"], display["error"]), (False, "no screen of 1536 x 2048"))
        self.screen.on = True
        self.display.retry()
        self.assertTrue(self.client.get("/api/display").json()["shown"])

    def test_play_tells_in_the_answer_whether_it_is_shown(self):
        self.screen.on = False
        response = self.upload(play=True)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["shown"])

    def restart(self, screen=None, **options):
        """A new server on the same state folder: returns its display, which restore() has filled."""
        display, _ = self.server(screen or FakeScreen(), **options)
        display.restore()
        display.retry()
        return display

    def test_shows_the_last_medium_again_after_a_restart(self):
        item = self.upload(play=True).json()
        display = self.restart()
        status = display.display_status()
        self.assertEqual((status["media"]["id"], status["shown"]), (item["id"], True))

    def test_shows_the_test_pattern_again_after_a_restart(self):
        self.show(test_pattern=True)
        self.assertEqual(self.restart().display_status()["source"], "test pattern")

    def test_shows_the_default_quilt_when_nothing_is_kept(self):
        display = self.restart(default="numbers")
        self.assertEqual(display.display_status()["source"], "test pattern")
        self.assertFalse((self.state / "shown.json").exists())  # Shown, not kept.

    def test_a_default_quilt_file_gives_its_layout_by_its_name(self):
        quilt = self.state / "default_qs8x6a0.75.png"
        quilt.write_bytes(self.quilt)
        status = self.restart(default=str(quilt)).display_status()
        self.assertEqual((status["source"], status["name"], status["shown"]),
                         ("default", "default_qs8x6a0.75.png", True))

    def test_a_kept_medium_wins_over_the_default(self):
        self.upload(play=True)
        self.assertEqual(self.restart(default="numbers").display_status()["source"], "media")

    def test_a_default_without_a_layout_shows_nothing(self):
        quilt = self.state / "default.png"
        quilt.write_bytes(self.quilt)
        with self.assertLogs("holo_pi.server", "WARNING"):
            display = self.restart(default=str(quilt))
        self.assertIsNone(display.display_status()["source"])

    def test_takes_the_quilt_of_a_version_before_the_library_into_it(self):
        (self.state / "quilt.png").write_bytes(self.quilt)
        (self.state / "quilt.json").write_text(json.dumps({
            "name": "old_qs8x6a0.75.png", "columns": 8, "rows": 6, "reverse": False, "width": 336, "height": 336,
            "uploaded": "2026-10-12T11:50:57+00:00", "file": "quilt.png"}))
        display = self.restart()
        status = display.display_status()
        self.assertEqual((status["source"], status["name"], status["shown"]), ("media", "old_qs8x6a0.75.png", True))
        self.assertEqual([item.name for item in display.library.list()], ["old_qs8x6a0.75.png"])
        self.assertFalse((self.state / "quilt.json").exists())


class ServerTest(ApiTest):
    def test_status_and_calibration(self):
        status = self.client.get("/api/status").json()
        self.assertEqual((status["screen"], status["display"]["source"]), ("fake", None))
        calibration = self.client.get("/api/calibration").json()
        self.assertEqual((calibration["serial"], calibration["width"]), ("LKG-PORT-00000", 1536))
        self.assertEqual(self.client.get("/api/status").json()["looking_glass"]["height"], 2048)

    def test_no_calibration_is_unavailable(self):
        display, client = self.server(FakeScreen(), calibration=None)
        display._read_calibration = lambda: (_ for _ in ()).throw(RuntimeError("no Looking Glass found"))
        response = client.get("/api/calibration")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "no Looking Glass found"})
        self.assertIn("no Looking Glass found", client.get("/api/status").json()["calibration_error"])

    def test_mounts_the_drive_only_when_asked(self):
        for mount, calls in [(False, 0), (True, 1)]:
            display = Display(FakeScreen(), state=self.state, mount=mount)
            missing = RuntimeError("no Looking Glass found")
            with mock.patch("holo_pi.server.find_calibration", side_effect=missing), \
                    mock.patch("holo_pi.server.mount_drives", return_value=[]) as mount_drives, \
                    self.assertRaisesRegex(RuntimeError, "no Looking Glass found"):
                display.calibration()
            self.assertEqual(mount_drives.call_count, calls)

    def test_documents_every_route(self):
        spec = self.client.get("/api/openapi.json").json()
        self.assertEqual(set(spec["paths"]), {"/api/media", "/api/media/{id}", "/api/media/{id}/content",
                                              "/api/display", "/api/status", "/api/calibration"})
        for methods in spec["paths"].values():
            for operation in methods.values():
                self.assertTrue(operation.get("summary") and operation.get("description"), operation)
                self.assertTrue(operation.get("tags"), operation)

    def test_serves_the_documentation(self):
        response = self.client.get("/api/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/openapi.json", response.text)

    def test_serves_the_web_page_and_the_documentation_from_its_files(self):
        web = self.state / "web"
        (web / "swagger-ui").mkdir(parents=True)
        (web / "index.html").write_text("<title>HoloPi</title>")
        (web / "swagger-ui" / "swagger-ui-bundle.js").write_text("// Swagger UI")
        client = TestClient(create_app(self.display, web))
        self.assertIn("HoloPi", client.get("/").text)
        self.assertIn("/api/docs/assets/swagger-ui-bundle.js", client.get("/api/docs").text)
        self.assertEqual(client.get("/api/docs/assets/swagger-ui-bundle.js").text, "// Swagger UI")
        self.assertEqual(client.get("/api/status").status_code, 200)  # The API before the web page.

    def test_without_a_web_page_home_leads_to_the_documentation(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual((response.status_code, response.headers["location"]), (307, "/api/docs"))


@unittest.skipIf(hologram_video is None, "no PyAV")
class VideoTest(ApiTest):
    """Hologram videos, of 3072 x 2048, as a Portrait's own, on a fake screen."""

    @classmethod
    def setUpClass(cls):
        cls.files = tempfile.TemporaryDirectory()
        cls.video = hologram_video(Path(cls.files.name) / "test.mkv", 1536, 2048, doubled=True).read_bytes()
        cls.other = hologram_video(Path(cls.files.name) / "other.mkv", 1536, 2048, list(reversed(COLOURS)),
                                   doubled=True).read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.files.cleanup()

    def upload_video(self, name="test.mkv", data=None, client=None, **fields):
        return self.upload(name, data or self.video, client, **fields)

    def test_plays_a_hologram_video(self):
        response = self.upload_video(play=True)
        self.assertEqual(response.status_code, 201, response.text)
        item = response.json()
        self.assertEqual((item["kind"], item["width"], item["fps"], item["codec"], item["columns"]),
                         ("hologram video", 3072, 24.0, "ffv1", None))
        self.assertIn("not H.265 (HEVC)", item["warning"])
        self.assertEqual(self.screen.shown.shape, (2048, 1536, 4))  # One pixel of each two, as XRGB8888.
        wait_for(lambda: self.screen.frames >= 6, "6 frames")  # It loops.
        display = self.client.get("/api/display").json()
        self.assertEqual((display["kind"], display["decoder"], display["shown"]), ("hologram video", "software", True))
        # The frames shown a second: how many depends on how fast the computer decodes, in software here.
        self.assertGreater(display["frame_rate"], 0)
        self.assertIn("not H.265 (HEVC)", display["warning"])

    def test_plays_a_video_once_then_another_in_a_loop(self):
        once = self.upload_video("once.mkv").json()
        loop = self.upload_video("loop.mkv", self.other).json()
        response = self.show(media_id=once["id"], then={"media_name": "loop.mkv"})
        self.assertEqual(response.status_code, 200, response.text)
        display = response.json()
        self.assertEqual((display["name"], display["then"]["id"]), ("once.mkv", loop["id"]))
        # After the first has played once, 4 frames, the second: the display says so, and nothing comes next.
        wait_for(lambda: self.client.get("/api/display").json()["name"] == "loop.mkv", "the loop")
        display = self.client.get("/api/display").json()
        self.assertEqual((display["media"]["id"], display["then"]), (loop["id"], None))
        self.assertEqual(json.loads((self.state / "shown.json").read_text()), {"id": loop["id"]})

    def test_then_needs_two_videos(self):
        video = self.upload_video().json()
        quilt = self.upload(play=False).json()
        for request, status in [({"media_id": video["id"], "then": {"media_id": quilt["id"]}}, 400),
                                ({"media_id": quilt["id"], "then": {"media_id": video["id"]}}, 400),
                                ({"media_id": video["id"], "then": {"media_id": "nope"}}, 404),
                                ({"media_id": video["id"], "then": {}}, 400),
                                ({"test_pattern": True, "then": {"media_id": video["id"]}}, 400)]:
            response = self.show(**request)
            self.assertEqual(response.status_code, status, (request, response.text))
            self.assertIn("error", response.json())

    def test_refuses_a_hologram_video_of_another_size(self):
        small = Path(self.files.name) / "small.mkv"
        response = self.upload_video(data=hologram_video(small, 64, 16).read_bytes())
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be 1536 x 2048, or 3072 x 2048", response.json()["error"])

    def test_a_quilt_replaces_the_video(self):
        self.upload_video(play=True)
        player = self.display.player
        self.upload(play=True)
        self.assertFalse(player.thread.is_alive() or player.decoder.is_alive())
        self.assertEqual(self.screen.shown.shape, (2048, 1536, 3))
        self.assertEqual(self.client.get("/api/display").json()["kind"], "quilt")
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 2)  # Both kept.

    def test_keeps_a_video_it_cannot_play_and_plays_it_later(self):
        item = self.upload_video().json()
        self.screen.on = False
        with mock.patch("holo_pi.video.RETRY_S", 0.05):
            self.assertEqual(self.show(media_id=item["id"]).status_code, 503)
            display = self.client.get("/api/display").json()
            self.assertEqual((display["shown"], display["error"]), (False, "no screen of 1536 x 2048"))
            self.screen.on = True
            wait_for(lambda: self.screen.frames >= 1, "a frame")
            self.assertTrue(self.client.get("/api/display").json()["shown"])

    def test_plays_the_last_video_again_after_a_restart(self):
        self.upload_video(play=True)
        self.display.stop()
        screen = FakeScreen()
        display, _ = self.server(screen, default="numbers")
        display.restore()
        display.retry()
        self.assertEqual(display.display_status()["kind"], "hologram video")
        wait_for(lambda: screen.frames >= 2, "2 frames")

    def test_waits_for_the_calibration_to_play(self):
        display, client = self.server(self.screen, calibration=None)
        missing = RuntimeError("no Looking Glass found")
        with mock.patch.object(display, "_read_calibration", side_effect=missing):
            item = self.upload_video(client=client).json()  # Its size is checked later.
            self.assertEqual(self.show(client=client, media_id=item["id"]).status_code, 503)
            self.assertEqual(display.display_status()["error"], "no Looking Glass found")
        display.calibration_path = VISUAL  # The Looking Glass is plugged in.
        display.retry()
        self.assertTrue(display.display_status()["shown"])

    def test_needs_pyav(self):
        with mock.patch("holo_pi.video._av", side_effect=NoPyAV("playing a video needs PyAV, python3-av")):
            response = self.upload_video()
        self.assertEqual(response.status_code, 501)
        self.assertIn("needs PyAV", response.json()["error"])
        self.assertEqual(self.client.get("/api/media").json()["items"], [])

    def test_removing_the_video_shown_stops_it(self):
        item = self.upload_video(play=True).json()
        player = self.display.player
        self.assertEqual(self.client.delete(f"/api/media/{item['id']}").status_code, 204)
        self.assertFalse(player.thread.is_alive() or player.decoder.is_alive())
        self.assertTrue(self.screen.cleared.is_set())

    def test_plays_without_a_state_folder(self):
        display = Display(self.screen, calibration=VISUAL, mount=False)
        self.displays.append(display)
        client = TestClient(create_app(display))
        item = self.upload_video(client=client, play=True).json()
        self.assertTrue(item["shown"])
        client.delete(f"/api/media/{item['id']}")
        self.assertEqual(display.library.list(), [])


@unittest.skipIf(hologram_video is None, "no PyAV")
class QuiltVideoTest(ApiTest):
    """Quilt videos: interleaved by the processor without a GPU, handed to the GPU's screen with one."""

    def setUp(self):
        super().setUp()
        self.video = quilt_video(self.state / "made.mkv", numbered_quilt()).read_bytes()
        (self.state / "made.mkv").unlink()

    def upload_video(self, name="test_qs8x6a0.75.mkv", client=None, **fields):
        return self.upload(name, self.video, client, **fields)

    def test_the_processor_interleaves_a_quilt_video_without_a_gpu(self):
        item = self.upload_video(play=True).json()
        self.assertEqual((item["kind"], item["columns"], item["rows"], item["width"], item["shown"]),
                         ("quilt video", 8, 6, 336, True))
        self.assertEqual(self.screen.shown.shape, (2048, 1536, 3))
        self.assertEqual(list(np.unique(self.screen.shown)), list(range(1, 49)))  # Every view seen: interleaved.

    def test_the_gpu_interleaves_a_quilt_video(self):
        screen = GpuScreen()
        _, client = self.server(screen)
        item = self.upload_video(client=client, play=True).json()
        self.assertTrue(item["shown"])
        self.assertEqual(screen.frames_shown[0], ("yuv420p", 336, 336, (8, 6)))
        self.assertIsNone(screen.shown)  # Nothing interleaved by the processor.
        self.assertEqual(client.get("/api/display").json()["shown_on"], "the fake GPU")

    def test_the_gpu_interleaves_a_quilt(self):
        screen = GpuScreen()
        _, client = self.server(screen)
        self.upload(client=client, play=True, reverse=True)
        self.assertEqual(screen.quilts, [((336, 336, 3), (8, 6), True)])

    def test_takes_the_layout_from_the_fields(self):
        item = self.upload_video("test.mkv", columns=8, rows=6, reverse=True).json()
        self.assertEqual((item["kind"], item["columns"], item["reverse"]), ("quilt video", 8, True))

    def test_a_video_without_a_layout_is_a_hologram_video(self):
        response = self.upload_video("test.mkv")
        self.assertEqual(response.status_code, 400)
        self.assertIn("is not a hologram for a screen of 1536 x 2048", response.json()["error"])

    def test_plays_the_last_quilt_video_again_after_a_restart(self):
        self.upload_video(play=True)
        self.display.stop()
        screen = GpuScreen()
        display, _ = self.server(screen)
        display.restore()
        display.retry()
        self.assertEqual((display.display_status()["kind"], display.display_status()["shown"]), ("quilt video", True))
        self.assertTrue(screen.frames_shown)


if __name__ == "__main__":
    unittest.main()
