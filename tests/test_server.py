"""Tests the HTTP API, with a fake screen: skipped without FastAPI, httpx and python-multipart. The tests of videos
are skipped without PyAV too."""

import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

try:
    from fastapi.testclient import TestClient

    from holo_pi.playlist import Entry
    from holo_pi.server import Display, create_app
except ImportError as error:  # The server's packages are optional.
    raise unittest.SkipTest(f"no server packages: {error}")

from test_holo_pi import VISUAL, numbered_quilt

try:
    from test_video import hologram_video, quilt_video

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
        self.events = []  # The transitions, and what is shown, in order.

    grades = True

    def show_quilt(self, picture, layout, calibration, reverse=False, grade=None):
        if not self.on:
            raise RuntimeError("no screen of 1536 x 2048")
        self.events.append("quilt")
        self.quilts.append((picture.shape, (layout.columns, layout.rows), reverse))
        self.grade = grade
        return "the fake GPU"

    def transition(self, kind, seconds):
        self.events.append((kind, seconds))

    def grade_quilt(self, picture, layout, calibration, grade):
        if not self.on:
            raise RuntimeError("no screen of 1536 x 2048")
        return 255 - picture

    def show_quilt_frame(self, frame, layout, calibration, reverse=False):
        self.events.append("frame")
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

    def test_orders_the_media_and_keeps_the_order(self):
        ids = [self.upload(f"{name}_qs8x6a0.75.png").json()["id"] for name in "abc"]
        response = self.client.put("/api/media/order", json={"ids": [ids[2], ids[0], ids[1]]})
        self.assertEqual(response.status_code, 200, response.text)
        names = ["c_qs8x6a0.75.png", "a_qs8x6a0.75.png", "b_qs8x6a0.75.png"]
        self.assertEqual([item["name"] for item in response.json()["items"]], names)
        # A replacement keeps its place, a new upload goes last, and a restart keeps the order.
        self.upload("a_qs8x6a0.75.png")
        self.upload("d_qs8x6a0.75.png")
        _, client = self.server(FakeScreen())
        self.assertEqual([item["name"] for item in client.get("/api/media").json()["items"]],
                         names + ["d_qs8x6a0.75.png"])

    def test_an_order_needs_every_id_once(self):
        a, b = (self.upload(f"{name}_qs8x6a0.75.png").json()["id"] for name in "ab")
        for ids, status, words in [([a], 400, "b_qs8x6a0.75.png left out"), ([a, a, b], 400, "given twice"),
                                   ([a, b, "nope"], 404, "no medium of the id 'nope'")]:
            response = self.client.put("/api/media/order", json={"ids": ids})
            self.assertEqual(response.status_code, status, ids)
            self.assertIn(words, response.json()["error"])
        self.assertEqual([item["id"] for item in self.client.get("/api/media").json()["items"]], [a, b])

    def rename(self, id, name):
        return self.client.put(f"/api/media/{id}/name", json={"name": name})

    def test_renames_a_medium_and_keeps_the_rest(self):
        before = self.upload().json()
        response = self.rename(before["id"], "  my héron_qs8x6a0.75.png ")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), dict(before, name="my héron_qs8x6a0.75.png"))
        content = self.client.get(f"/api/media/{before['id']}/content")
        self.assertEqual(content.content, self.quilt)
        self.assertIn("my%20h%C3%A9ron_qs8x6a0.75.png", content.headers["content-disposition"])
        self.assertEqual(self.show(media_name="my héron_qs8x6a0.75.png").status_code, 200)
        self.assertEqual(self.show(media_name=before["name"]).status_code, 404)
        self.assertEqual(self.client.get(f"/api/media/{before['id']}").json()["columns"], 8)

    def test_a_rename_is_kept_after_a_restart(self):
        id = self.upload().json()["id"]
        self.rename(id, "other.png")
        _, client = self.server(FakeScreen())
        self.assertEqual(client.get(f"/api/media/{id}").json()["name"], "other.png")

    def test_renaming_what_is_shown_leaves_it_shown_under_its_new_name(self):
        id = self.upload(play=True).json()["id"]
        frames = self.screen.frames
        self.rename(id, "other.png")
        status = self.client.get("/api/display").json()
        self.assertEqual((status["name"], status["media"]["name"], status["shown"]), ("other.png", "other.png", True))
        self.assertEqual(self.screen.frames, frames)

    def test_a_new_name_keeps_the_extension(self):
        id = self.upload().json()["id"]
        for name, kept in [("wasp", "wasp.png"), ("wasp.PNG", "wasp.PNG"), ("wasp_qs8x6a0.75", "wasp_qs8x6a0.75.PNG"),
                           ("wasp.jpg", "wasp.jpg.PNG")]:
            self.assertEqual(self.rename(id, name).json()["name"], kept)

    def test_refuses_a_name_no_file_can_have(self):
        before = self.upload().json()
        for name in ("", "   ", ".png", " .png", "..", "a/b.png", "a\\b.png", "a\nb.png", "a" * 300):
            response = self.rename(before["id"], name)
            self.assertEqual(response.status_code, 400, name)
            self.assertIn("a name cannot", response.json()["error"])
        self.assertEqual(self.client.get(f"/api/media/{before['id']}").json()["name"], before["name"])

    def test_refuses_the_name_of_another_medium_but_not_its_own(self):
        id = self.upload().json()["id"]
        other = self.upload("other_qs8x6a0.75.png").json()
        response = self.rename(id, other["name"])
        self.assertEqual(response.status_code, 409)
        self.assertIn("another other_qs8x6a0.75.png", response.json()["error"])
        self.assertEqual(self.rename(other["id"], other["name"]).status_code, 200)
        self.assertEqual(self.rename("00000000", "new.png").status_code, 404)

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
            self.assertIn("give one of media_id, media_name, test_pattern and playlist", response.json()["error"])

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
        self.assertEqual(set(spec["paths"]), {"/api/media", "/api/media/order", "/api/media/{id}",
                                              "/api/media/{id}/content", "/api/media/{id}/name",
                                              "/api/media/{id}/grade", "/api/media/{id}/graded-copies",
                                              "/api/grade-parameters", "/api/playlist",
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


class GradeTest(ApiTest):
    """The grades, on a fake screen with a GPU."""

    def setUp(self):
        super().setUp()
        self.screen = GpuScreen()
        self.display, self.client = self.server(self.screen)
        self.id = self.upload(play=True).json()["id"]
        self.path = f"/api/media/{self.id}/grade"

    def test_lists_the_parameters(self):
        items = self.client.get("/api/grade-parameters").json()["items"]
        self.assertIn({"id": "exposure", "label": "Exposure", "section": "Light", "minimum": -5, "maximum": 5,
                       "default": 0, "decimals": 2, "description": "The light, in stops: 1 is twice as much."}, items)
        self.assertEqual(set(self.client.get(self.path).json()), {item["id"] for item in items} | {"enabled"})

    def test_a_quilt_has_no_grade_at_first(self):
        grade = self.client.get(self.path).json()
        self.assertEqual((grade["enabled"], grade["exposure"], grade["midtone_split"]), (True, 0, 50))
        self.assertIsNone(self.screen.grade)

    def test_grades_the_quilt_shown_at_once(self):
        response = self.client.put(self.path, json={"exposure": 1.5, "saturation": -20})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["exposure"], response.json()["contrast"]), (1.5, 0))
        self.assertEqual(self.screen.grade.values, {"exposure": 1.5, "saturation": -20})
        # A value not given is at its default again.
        self.client.put(self.path, json={"contrast": 10})
        self.assertEqual(self.screen.grade.values, {"contrast": 10})
        self.assertEqual(self.client.get(self.path).json()["exposure"], 0)

    def test_grades_a_quilt_not_shown_without_showing_it(self):
        self.client.delete("/api/display")
        shown = len(self.screen.quilts)
        self.assertEqual(self.client.put(self.path, json={"exposure": 1}).status_code, 200)
        self.assertEqual(len(self.screen.quilts), shown)
        self.show(media_id=self.id)
        self.assertEqual(self.screen.grade.values, {"exposure": 1})

    def test_a_grade_switched_off_keeps_its_values(self):
        self.client.put(self.path, json={"exposure": 1, "enabled": False})
        self.assertFalse(self.screen.grade.changes)
        self.assertEqual(self.client.get(self.path).json()["exposure"], 1)

    def test_a_medium_says_whether_it_is_graded(self):
        def grades():
            return (self.client.get(f"/api/media/{self.id}").json()["grade"],
                    self.client.get("/api/media").json()["items"][0]["grade"],
                    self.client.get("/api/display").json()["media"]["grade"])

        self.assertEqual(grades(), (None, None, None))
        self.client.put(self.path, json={"exposure": 1})
        self.assertEqual(grades(), ("on", "on", "on"))
        self.assertIsNone(self.save().json()["grade"])  # The copy has it in its pixels.
        self.client.put(self.path, json={"exposure": 1, "enabled": False})
        self.assertEqual(grades(), ("off", "off", "off"))
        self.client.put(self.path, json={"enabled": False})  # Nothing is left to switch off.
        self.assertEqual(grades(), (None, None, None))
        self.client.put(self.path, json={"exposure": 1})
        self.client.delete(self.path)
        self.assertEqual(grades(), (None, None, None))

    def test_removing_the_grade_shows_the_quilt_as_uploaded(self):
        self.client.put(self.path, json={"exposure": 1})
        self.assertEqual(self.client.delete(self.path).status_code, 204)
        self.assertIsNone(self.screen.grade)
        self.assertEqual(self.client.get(self.path).json()["exposure"], 0)

    def save(self):
        return self.client.post(f"/api/media/{self.id}/graded-copies")

    def test_saves_the_graded_quilt_as_a_new_one(self):
        self.client.put(self.path, json={"exposure": 1})
        response = self.save()
        self.assertEqual(response.status_code, 201, response.text)
        saved = response.json()
        self.assertEqual(response.headers["location"], f"/api/media/{saved['id']}")
        self.assertEqual((saved["name"], saved["kind"], saved["columns"], saved["rows"], saved["shown"]),
                         ("test-graded_qs8x6a0.75.png", "quilt", 8, 6, False))
        content = self.client.get(f"/api/media/{saved['id']}/content").content
        np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(content))), 255 - numbered_quilt())
        # The original, its grade and what is shown stay, and the new quilt has no grade: it is in its pixels.
        self.assertEqual(self.client.get(self.path).json()["exposure"], 1)
        self.assertEqual(self.client.get(f"/api/media/{self.id}/content").content, self.quilt)
        self.assertEqual(self.client.get("/api/display").json()["media"]["id"], self.id)
        self.assertEqual(self.client.get(f"/api/media/{saved['id']}/grade").json()["exposure"], 0)

    def test_saves_each_time_under_another_name(self):
        self.client.put(self.path, json={"exposure": 1})
        names = [self.save().json()["name"] for _ in range(3)]
        self.assertEqual(names, ["test-graded_qs8x6a0.75.png", "test-graded-2_qs8x6a0.75.png",
                                 "test-graded-3_qs8x6a0.75.png"])
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 4)

    def test_saves_a_quilt_whose_name_has_no_layout_with_its_layout_and_its_order(self):
        self.id = self.upload("plain.png", columns=8, rows=6, reverse=True).json()["id"]
        self.client.put(f"/api/media/{self.id}/grade", json={"exposure": 1})
        saved = self.save().json()
        self.assertEqual((saved["name"], saved["columns"], saved["rows"], saved["reverse"]),
                         ("plain-graded.png", 8, 6, True))

    def test_saves_only_a_grade_that_changes_something(self):
        self.assertEqual(self.save().status_code, 400)
        self.client.put(self.path, json={"exposure": 1, "enabled": False})
        self.assertEqual(self.save().status_code, 400)
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 1)

    def test_saving_needs_the_gpu_its_screen_and_a_known_id(self):
        self.client.put(self.path, json={"exposure": 1})
        self.screen.on = False
        self.assertEqual(self.save().status_code, 503)
        self.assertEqual(self.client.post("/api/media/00000000/graded-copies").status_code, 404)
        _, client = self.server(FakeScreen())
        self.assertEqual(client.post(f"/api/media/{self.id}/graded-copies").status_code, 501)
        self.assertEqual(len(self.client.get("/api/media").json()["items"]), 1)

    def test_the_file_stays_as_uploaded(self):
        self.client.put(self.path, json={"exposure": 1})
        self.assertEqual(self.client.get(f"/api/media/{self.id}/content").content, self.quilt)

    def test_the_grade_is_kept_after_a_restart(self):
        self.client.put(self.path, json={"exposure": 1})
        self.display.stop()  # Writes the grade, without waiting for the last change to be a while ago.
        screen = GpuScreen()
        display, client = self.server(screen)
        display.restore()
        display.retry()
        self.assertEqual(screen.grade.values, {"exposure": 1})
        self.assertEqual(client.get(self.path).json()["exposure"], 1)

    def test_the_index_is_written_a_while_after_the_last_change(self):
        index = self.state / "library" / "index.json"
        with mock.patch("holo_pi.library.SAVE_S", 0.05):
            self.client.put(self.path, json={"exposure": 1})
            self.assertIsNone(json.loads(index.read_text())[0]["grade"])
            wait_for(lambda: self.display.library.timer is None, "the index")
        self.assertEqual(json.loads(index.read_text())[0]["grade"], {"exposure": 1, "enabled": True})

    def test_another_upload_of_the_name_starts_without_a_grade(self):
        self.client.put(self.path, json={"exposure": 1})
        self.upload()
        self.assertEqual(self.client.get(self.path).json()["exposure"], 0)

    def test_refuses_a_value_out_of_its_range(self):
        response = self.client.put(self.path, json={"exposure": 6})
        self.assertEqual(response.status_code, 422)
        self.assertIn("exposure", response.json()["error"])

    def test_an_unknown_id_is_not_found(self):
        for method in ("get", "put", "delete"):
            options = {"json": {}} if method == "put" else {}
            self.assertEqual(getattr(self.client, method)("/api/media/00000000/grade", **options).status_code, 404)

    def test_needs_the_gpu(self):
        _, client = self.server(FakeScreen())
        response = client.put(self.path, json={"exposure": 1})
        self.assertEqual(response.status_code, 501)
        self.assertIn("--screen gl", response.json()["error"])

    def test_keeps_the_grade_of_a_quilt_it_cannot_show(self):
        self.screen.on = False
        self.assertEqual(self.client.put(self.path, json={"exposure": 1}).status_code, 200)
        status = self.client.get("/api/display").json()
        self.assertEqual((status["shown"], status["error"]), (False, "no screen of 1536 x 2048"))
        self.screen.on = True
        self.display.retry()
        self.assertEqual(self.screen.grade.values, {"exposure": 1})
        self.assertTrue(self.client.get("/api/display").json()["shown"])

    def test_a_renamed_quilt_keeps_its_grade(self):
        self.client.put(self.path, json={"exposure": 1})
        self.client.put(f"/api/media/{self.id}/name", json={"name": "other_qs8x6a0.75.png"})
        self.assertEqual(self.client.get(self.path).json()["exposure"], 1)
        self.assertEqual(self.save().json()["name"], "other-graded_qs8x6a0.75.png")

    @unittest.skipIf(hologram_video is None, "no PyAV")
    def test_a_video_cannot_be_graded(self):
        video = quilt_video(self.state / "test_qs8x6a0.75.mkv", numbered_quilt()).read_bytes()
        id = self.upload("video_qs8x6a0.75.mkv", video).json()["id"]
        response = self.client.put(f"/api/media/{id}/grade", json={"exposure": 1})
        self.assertEqual(response.status_code, 400)
        self.assertIn("only a quilt", response.json()["error"])


class PlaylistTest(ApiTest):
    """The playlist, of quilts, on a fake screen."""

    def setUp(self):
        super().setUp()
        self.ids = [self.upload(f"{name}_qs8x6a0.75.png").json()["id"] for name in "abc"]

    def put(self, *items, client=None, **fields):
        return (client or self.client).put("/api/playlist", json={"items": list(items), **fields})

    def quick(self, *ids, seconds=0.2, repeat=True, display=None):
        """A playlist of these media, each shown for less than the API allows."""
        (display or self.display).playlist.set(repeat, [Entry(id, seconds=seconds) for id in ids])

    def status(self, client=None):
        return (client or self.client).get("/api/display").json()

    def watch(self, until, what="the playlist"):
        """The ids shown, one after the other, until `until` of them is true."""
        seen = []

        def look():
            medium = self.status()["media"]
            if medium and (not seen or seen[-1] != medium["id"]):
                seen.append(medium["id"])
            return until(seen)
        wait_for(look, what)
        return seen

    def test_is_empty_at_first(self):
        self.assertEqual(self.client.get("/api/playlist").json(), {"repeat": True, "transition": "cut", "transition_seconds": 1, "items": []})
        response = self.show(playlist=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn("the playlist is empty", response.json()["error"])
        self.assertIsNone(self.status()["playlist"])

    def test_keeps_the_playlist_in_the_librarys_order_also_after_a_restart(self):
        a, b, c = self.ids
        response = self.put({"media_id": c, "seconds": 3.5}, {"media_id": a}, repeat=False)
        self.assertEqual(response.status_code, 200, response.text)
        kept = {"repeat": False, "transition": "cut", "transition_seconds": 1,
                "items": [{"media_id": a, "enabled": True, "seconds": 10, "loops": None},
                          {"media_id": c, "enabled": True, "seconds": 3.5, "loops": None}]}
        self.assertEqual(response.json(), kept)
        _, client = self.server(FakeScreen())
        self.assertEqual(client.get("/api/playlist").json(), kept)
        self.client.put("/api/media/order", json={"ids": [c, b, a]})
        self.assertEqual([item["media_id"] for item in self.client.get("/api/playlist").json()["items"]], [c, a])

    def test_keeps_the_transition_also_after_a_restart(self):
        response = self.put(transition="cross fade", transition_seconds=2.5)
        self.assertEqual(response.status_code, 200, response.text)
        _, client = self.server(FakeScreen())
        kept = client.get("/api/playlist").json()
        self.assertEqual((kept["transition"], kept["transition_seconds"]), ("cross fade", 2.5))
        for wrong in ({"transition": "wipe"}, {"transition_seconds": 0}, {"transition_seconds": 11}):
            self.assertEqual(self.put(**wrong).status_code, 422, wrong)

    def test_takes_a_playlist_kept_before_there_were_transitions(self):
        (self.state / "playlist.json").write_text(json.dumps({"repeat": False, "items": [{"media_id": self.ids[0]}]}))
        _, client = self.server(FakeScreen())
        kept = client.get("/api/playlist").json()
        self.assertEqual((kept["repeat"], kept["transition"], len(kept["items"])), (False, "cut", 1))

    def test_takes_a_playlist_kept_with_a_transition_that_is_gone(self):
        (self.state / "playlist.json").write_text(json.dumps({
            "repeat": True, "transition": "wipe", "transition_seconds": 2, "items": [{"media_id": self.ids[0]}]}))
        _, client = self.server(FakeScreen())
        kept = client.get("/api/playlist").json()
        self.assertEqual((kept["transition"], len(kept["items"])), ("cut", 1))

    def test_without_a_gpu_it_plays_without_transitions(self):
        a, b, _ = self.ids
        self.display.playlist.set(True, [Entry(a, seconds=0.2), Entry(b, seconds=0.2)], "cross fade")
        self.show(playlist=True)
        self.assertEqual(self.watch(lambda seen: len(seen) == 3), [a, b, a])

    def test_setting_it_changes_nothing_on_the_screen(self):
        self.put({"media_id": self.ids[0]})
        self.assertEqual(self.screen.frames, 0)

    def test_refuses_what_it_cannot_play(self):
        a = self.ids[0]
        for items, status, words in [([{"media_id": "nope"}], 404, "no medium of the id 'nope'"),
                                     ([{"media_id": a}, {"media_id": a}], 400, "given twice"),
                                     ([{"media_id": a, "loops": 2}], 400, "is a quilt: give seconds"),
                                     ([{"media_id": a, "seconds": 0}], 422, "seconds")]:
            response = self.put(*items)
            self.assertEqual(response.status_code, status, items)
            self.assertIn(words, response.json()["error"])
        self.assertEqual(self.client.get("/api/playlist").json()["items"], [])

    def test_a_damaged_file_is_an_empty_playlist(self):
        (self.state / "playlist.json").write_text('{"items": 3}')
        with self.assertLogs("holo_pi.playlist", "WARNING"):
            _, client = self.server(FakeScreen())
        self.assertEqual(client.get("/api/playlist").json()["items"], [])

    def test_plays_one_after_the_other_and_again(self):
        a, b, c = self.ids
        self.quick(a, b, c)
        response = self.show(playlist=True)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["media"]["id"], response.json()["playlist"]),
                         (a, {"position": 1, "count": 3}))
        self.assertEqual(self.watch(lambda seen: len(seen) == 5), [a, b, c, a, b])

    def test_leaves_out_the_media_not_enabled(self):
        a, b, c = self.ids
        self.display.playlist.set(True, [Entry(a, seconds=0.2), Entry(b, enabled=False), Entry(c, seconds=0.2)])
        self.show(playlist=True)
        self.assertEqual(self.watch(lambda seen: len(seen) == 3), [a, c, a])
        self.assertEqual(self.status()["playlist"]["count"], 2)

    def test_shows_each_for_its_time(self):
        a, b, _ = self.ids
        self.display.playlist.set(True, [Entry(a, seconds=0.6), Entry(b, seconds=0.1)])
        self.show(playlist=True)
        start = time.monotonic()
        wait_for(lambda: self.status()["media"]["id"] == b, "the second")
        self.assertGreater(time.monotonic() - start, 0.5)

    def test_without_repeat_it_ends_black(self):
        self.quick(*self.ids[:2], repeat=False)
        self.show(playlist=True)
        wait_for(self.screen.cleared.is_set, "black")
        wait_for(lambda: self.status()["source"] is None, "nothing")
        self.assertIsNone(self.status()["playlist"])
        self.assertFalse((self.state / "shown.json").exists())

    def test_showing_something_else_ends_it(self):
        a, b, c = self.ids
        for other, source in [({"media_id": c}, "media"), ({"test_pattern": True}, "test pattern")]:
            self.quick(a, b)
            self.show(playlist=True)
            run = self.display.run
            self.show(**other)
            run.thread.join(5)
            self.assertFalse(run.thread.is_alive())
            threading.Event().wait(0.4)  # More than the time of a medium.
            self.assertEqual((self.status()["source"], self.status()["playlist"]), (source, None))

    def test_black_ends_it(self):
        self.quick(*self.ids)
        self.show(playlist=True)
        run = self.display.run
        self.client.delete("/api/display")
        run.thread.join(5)
        threading.Event().wait(0.4)
        self.assertEqual((self.status()["source"], self.screen.shown), (None, None))

    def test_an_upload_shown_ends_it_and_one_only_kept_does_not(self):
        self.quick(*self.ids)
        self.show(playlist=True)
        self.upload("d_qs8x6a0.75.png")
        self.assertIsNotNone(self.status()["playlist"])
        self.upload("e_qs8x6a0.75.png", play=True)
        self.assertIsNone(self.status()["playlist"])

    def test_playing_it_again_starts_it_again(self):
        a, b, _ = self.ids
        self.display.playlist.set(True, [Entry(a, seconds=0.1), Entry(b, seconds=60)])
        self.show(playlist=True)
        wait_for(lambda: self.status()["media"]["id"] == b, "the second")
        first = self.display.run
        self.assertEqual(self.show(playlist=True).json()["media"]["id"], a)
        first.thread.join(5)
        self.assertFalse(first.thread.is_alive())

    def test_a_change_counts_from_the_next_medium_on(self):
        a, b, c = self.ids
        self.quick(a, b, seconds=0.4)
        self.show(playlist=True)
        self.quick(a, c, seconds=0.4)
        self.assertEqual(self.status()["media"]["id"], a)
        self.assertEqual(self.watch(lambda seen: len(seen) == 3), [a, c, a])

    def test_emptying_it_ends_it(self):
        self.quick(*self.ids)
        self.show(playlist=True)
        self.put()
        wait_for(lambda: self.status()["source"] is None, "black")

    def test_removing_the_medium_shown_goes_on_to_the_next(self):
        a, b, c = self.ids
        self.quick(a, b, c, seconds=60)
        self.show(playlist=True)
        for gone, then in [(a, b), (b, c)]:
            self.assertEqual(self.client.delete(f"/api/media/{gone}").status_code, 204)
            wait_for(lambda: (self.status()["media"] or {}).get("id") == then, "the next")
        self.client.delete(f"/api/media/{c}")
        wait_for(lambda: self.status()["source"] is None, "black")

    def test_removing_every_medium_ends_it(self):
        self.quick(*self.ids)
        self.show(playlist=True)
        self.client.delete("/api/media")
        self.assertEqual((self.status()["source"], self.status()["playlist"]), (None, None))

    def test_waits_for_the_looking_glass(self):
        a, b, _ = self.ids
        self.quick(a, b)
        self.screen.on = False
        response = self.show(playlist=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("no screen of 1536 x 2048", response.json()["error"])
        threading.Event().wait(0.5)  # Nobody has seen the first one: it is still its turn.
        status = self.status()
        self.assertEqual((status["media"]["id"], status["shown"], status["playlist"]["position"]), (a, False, 1))
        self.screen.on = True
        self.display.retry()
        self.assertTrue(self.status()["shown"])
        wait_for(lambda: self.status()["media"]["id"] == b, "the second")

    def test_leaves_out_a_damaged_file(self):
        a, b, c = self.ids
        self.display.library.path(self.display.library.find(id=b)).write_bytes(b"damaged")
        self.quick(a, b, c)
        with self.assertLogs("holo_pi.playlist", "WARNING"):
            self.show(playlist=True)
            self.assertEqual(self.watch(lambda seen: len(seen) == 3), [a, c, a])

    def test_says_so_when_nothing_can_be_shown(self):
        a = self.ids[0]
        self.display.library.path(self.display.library.find(id=a)).write_bytes(b"damaged")
        self.quick(a)
        response = self.show(playlist=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("a_qs8x6a0.75.png", response.json()["error"])
        self.assertIn("a_qs8x6a0.75.png", self.status()["error"])

    def test_plays_again_after_a_restart(self):
        self.quick(*self.ids)
        self.show(playlist=True)
        self.display.stop()
        screen = FakeScreen()
        display, client = self.server(screen)
        display.restore()
        display.retry()
        wait_for(lambda: self.status(client)["shown"], "the first")
        self.assertEqual(self.status(client)["playlist"]["count"], 3)
        wait_for(lambda: screen.frames >= 3, "the others")

    def test_a_restart_after_its_media_are_gone_shows_the_default(self):
        self.quick(self.ids[0])
        self.show(playlist=True)
        self.display.stop()
        self.display.library.remove(self.display.library.find(id=self.ids[0]))
        display, client = self.server(FakeScreen(), default="numbers")
        display.restore()
        display.retry()
        self.assertEqual((self.status(client)["source"], self.status(client)["playlist"]), ("test pattern", None))


@unittest.skipIf(hologram_video is None, "no PyAV")
class VideoPlaylistTest(ApiTest):
    """The playlist, of a quilt video and a quilt, on a fake screen with a GPU."""

    def setUp(self):
        super().setUp()
        self.screen = GpuScreen()
        self.display, self.client = self.server(self.screen)
        video = quilt_video(self.state / "made.mkv", numbered_quilt()).read_bytes()
        self.video = self.upload("video_qs8x6a0.75.mkv", video).json()["id"]
        self.quilt_id = self.upload().json()["id"]

    def test_a_video_takes_loops_once_by_default(self):
        response = self.client.put("/api/playlist", json={"items": [{"media_id": self.video}]})
        self.assertEqual(response.json()["items"][0], {"media_id": self.video, "enabled": True, "seconds": None,
                                                       "loops": 1})
        response = self.client.put("/api/playlist", json={"items": [{"media_id": self.video, "seconds": 3}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("give loops", response.json()["error"])

    def test_plays_a_video_its_loops_then_the_quilt(self):
        self.display.playlist.set(True, [Entry(self.video, loops=3), Entry(self.quilt_id, seconds=60)])
        self.show(playlist=True)
        wait_for(lambda: self.screen.quilts, "the quilt")
        # 3 times 4 frames; a busy computer may skip a late one, but none is shown beyond.
        self.assertLessEqual(len(self.screen.frames_shown), 12)
        self.assertGreater(len(self.screen.frames_shown), 8)
        status = self.client.get("/api/display").json()
        self.assertEqual((status["kind"], status["playlist"]), ("quilt", {"position": 2, "count": 2}))
        self.assertIsNone(self.display.player)

    def test_goes_from_the_quilt_to_the_video_and_back(self):
        self.display.playlist.set(True, [Entry(self.video), Entry(self.quilt_id, seconds=0.1)])
        self.show(playlist=True)
        wait_for(lambda: len(self.screen.quilts) >= 3, "three rounds")

    def test_each_medium_comes_with_the_transition(self):
        self.display.playlist.set(True, [Entry(self.video), Entry(self.quilt_id, seconds=60)], "cross fade", 0.5)
        self.show(playlist=True)
        wait_for(lambda: self.screen.quilts, "the quilt")
        # Begun after the last frame of the video, whose player has stopped, and before the quilt.
        events = [event for event, after in zip(self.screen.events, self.screen.events[1:] + [None]) if event != after]
        self.assertEqual(events, [("cross fade", 0.5), "frame", ("cross fade", 0.5), "quilt"])

    def test_what_is_shown_by_itself_comes_at_once(self):
        self.display.playlist.set(True, [Entry(self.quilt_id, seconds=60)], "cross fade")
        self.show(playlist=True)
        for other in ({"media_id": self.quilt_id}, {"test_pattern": True}):
            self.screen.events.clear()
            self.show(**other)
            self.assertEqual(self.screen.events, [("cut", 1), "quilt"])

    def test_the_only_medium_stays_without_a_transition(self):
        self.display.playlist.set(True, [Entry(self.quilt_id, seconds=0.1)], "cross fade")
        self.show(playlist=True)
        wait_for(lambda: len(self.screen.quilts) >= 3, "the same again")
        self.assertEqual(self.screen.events[:4], [("cross fade", 1), "quilt", ("cut", 1), "quilt"])

    def test_a_video_shown_by_itself_still_loops(self):
        self.display.playlist.set(True, [Entry(self.video), Entry(self.quilt_id, seconds=60)])
        self.show(playlist=True)
        self.show(media_id=self.video)
        self.screen.frames_shown.clear()
        wait_for(lambda: len(self.screen.frames_shown) >= 10, "more than two rounds")

    def test_leaves_out_a_video_of_a_damaged_file(self):
        path = self.display.library.path(self.display.library.find(id=self.video))
        path.write_bytes(b"damaged")
        self.display.playlist.set(True, [Entry(self.video), Entry(self.quilt_id, seconds=60)])
        with self.assertLogs("holo_pi.playlist", "WARNING"):
            response = self.show(playlist=True)
        self.assertEqual((response.status_code, response.json()["media"]["id"]), (200, self.quilt_id))

    def test_a_video_waits_for_the_looking_glass_and_then_plays_whole(self):
        self.display.playlist.set(True, [Entry(self.video), Entry(self.quilt_id, seconds=60)])
        on = self.screen.show_quilt_frame

        def show_quilt_frame(*arguments):
            if not self.screen.on:
                raise RuntimeError("no screen of 1536 x 2048")
            return on(*arguments)
        self.screen.show_quilt_frame = show_quilt_frame
        self.screen.on = False
        with mock.patch("holo_pi.video.RETRY_S", 0.05):
            self.assertEqual(self.show(playlist=True).status_code, 503)
            threading.Event().wait(0.5)  # More than its 4 frames take.
            self.assertEqual(self.client.get("/api/display").json()["media"]["id"], self.video)
            self.screen.on = True
            wait_for(lambda: self.screen.quilts, "the quilt")
        self.assertGreaterEqual(len(self.screen.frames_shown), 3)


@unittest.skipIf(hologram_video is None, "no PyAV")
class VideoTest(ApiTest):
    """Hologram videos, of 3072 x 2048, as a Portrait's own, on a fake screen."""

    @classmethod
    def setUpClass(cls):
        cls.files = tempfile.TemporaryDirectory()
        cls.video = hologram_video(Path(cls.files.name) / "test.mkv", 1536, 2048, doubled=True).read_bytes()

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
