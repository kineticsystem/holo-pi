"""The playlist: which media of the library play one after the other, and for how long each.

A quilt is shown for some seconds, a video plays some times over. They play in
the library's order: the library has the one order there is. The playlist is
kept in playlist.json, with the settings of the media not played too, so that
they are there when they are played again.

Run plays it, on a thread of its own: it shows a medium on the Display, waits
until its time is over, and asks the playlist for the next one, so that a change
of the playlist or of the library counts from the next medium on.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass
from typing import Optional

from .quilt import read_quilt
from .video import Unplayable

log = logging.getLogger(__name__)

# How long a quilt is shown, and how often a video plays, unless the playlist says otherwise.
SECONDS, LOOPS = 10, 1
# How often a run looks whether what it waits for has happened.
POLL_S = 0.1
# How long a run waits when none of the playlist's media can be shown, e.g. their files are damaged, to try again.
RETRY_S = 5


class EmptyPlaylist(ValueError):
    """Nothing to play: no medium of the library is enabled in the playlist."""


@dataclass
class Entry:
    media_id: str
    enabled: bool = True  # Whether it is played: otherwise only its settings are kept.
    seconds: Optional[float] = None  # How long a quilt is shown; None for a video.
    loops: Optional[int] = None  # How often a video plays; None for a quilt.


class Playlist:
    """The playlist of `library`, kept in the file `path`. Thread-safe."""

    def __init__(self, path, library):
        self.path = path
        self.library = library
        self.lock = threading.RLock()
        self.repeat = True  # Whether it starts again after the last medium, or ends, black.
        self.kept = {}  # The entries, by their media's ids, also of media gone since.
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            self.kept = {entry["media_id"]: Entry(**entry) for entry in data["items"]}
            self.repeat = bool(data["repeat"])
        except (OSError, ValueError, TypeError, KeyError) as error:
            log.warning("Cannot read the playlist %s: %s", self.path, error)

    def set(self, repeat, entries):
        """Replaces the playlist. Raises KeyError, its message the reason, for a medium the library does not have,
        and ValueError for one given twice, seconds for a video or loops for a quilt."""
        with self.lock:
            kept = {}
            for entry in entries:
                item = self.library.find(id=entry.media_id)
                if item is None:
                    raise KeyError(f"no medium of the id {entry.media_id!r}")
                if item.id in kept:
                    raise ValueError(f"{item.name} is given twice")
                if item.is_video and entry.seconds is not None:
                    raise ValueError(f"{item.name} is a {item.kind}: give loops, how often it plays, not seconds")
                if not item.is_video and entry.loops is not None:
                    raise ValueError(f"{item.name} is a quilt: give seconds, how long it is shown, not loops")
                kept[item.id] = entry
            before = self.kept, self.repeat
            self.kept, self.repeat = kept, repeat
            try:
                self._save()
            except OSError:
                self.kept, self.repeat = before
                raise

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"repeat": self.repeat, "items": [asdict(entry) for entry in self.kept.values()]}
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2))
        temporary.replace(self.path)

    def _entry(self, item):
        """An item's entry, with what it does not say at its default; None if it has none."""
        entry = self.kept.get(item.id)
        if entry is None:
            return None
        if item.is_video:
            return Entry(item.id, entry.enabled, None, entry.loops or LOOPS)
        return Entry(item.id, entry.enabled, entry.seconds or SECONDS, None)

    def entries(self):
        """The entries of the library's media, in its order, also of those not played."""
        with self.lock:
            return [entry for entry in map(self._entry, self.library.list()) if entry is not None]

    def playable(self):
        """The ids of the media played, in order."""
        return [entry.media_id for entry in self.entries() if entry.enabled]

    def next(self, id=None, place=0):
        """The medium to play after the one of `id`, at `place` in the library before it was gone, if it is; the first
        one without `id`. Returns (item, entry, place), or None if the playlist is over."""
        with self.lock:
            items = self.library.list()
            places = [place for place, item in enumerate(items) if item.id == id]
            start = places[0] + 1 if places else place
            rest = list(range(start, len(items)))
            if self.repeat:
                rest += range(min(start, len(items)))
            for place in rest:
                entry = self._entry(items[place])
                if entry is not None and entry.enabled:
                    return items[place], entry, place
            return None


class Run:
    """The playlist, playing on `display`, until it is over or end() is called, e.g. as something else is shown.

    `started` is set once the first medium is shown, or cannot be yet; `error` says why not, if so. A medium that
    cannot be shown whatever the Looking Glass, e.g. whose file is damaged, is left out; one that cannot be shown yet,
    e.g. because the Looking Glass is switched off, is waited for."""

    def __init__(self, playlist, display):
        self.playlist = playlist
        self.display = display
        self.id = None  # The medium playing, and its place in the library.
        self.place = 0
        self.error = None
        self.started = threading.Event()
        self.over = threading.Event()
        self.wake = threading.Event()  # Set to stop waiting for the medium playing.
        self.thread = threading.Thread(target=self._run, name="playlist", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def end(self):
        """Ends it, without waiting for its thread, which shows nothing any more."""
        self.over.set()
        self.wake.set()

    def skip(self, id):
        """Goes on to the next medium, if the one of `id` is playing."""
        if self.id == id:
            self.wake.set()

    def progress(self):
        """Which medium of the playlist is playing, from 1, or None if it is not one of them any more, and of how
        many."""
        ids = self.playlist.playable()
        return {"position": ids.index(self.id) + 1 if self.id in ids else None, "count": len(ids)}

    def _run(self):
        failed = 0  # How many media could not be shown, one after the other.
        while True:
            self.wake.clear()
            if self.over.is_set():
                break
            found = self.playlist.next(self.id, self.place)
            if found is None:
                self.display.finish(self)
                break
            item, entry, self.place = found
            self.id = item.id
            try:
                self._play(item, entry)
                failed = 0
            except (Unplayable, ValueError) as error:
                log.warning("The playlist leaves out %s: %s", item.name, error)
                self.error = str(error)
                failed += 1
                if failed >= len(self.playlist.playable()):  # All of them.
                    failed = 0
                    self.started.set()
                    self.over.wait(RETRY_S)
            except Exception:  # A bug, or e.g. a disk that fails: the server goes on, and what is shown stays.
                log.exception("The playlist stops at %s", item.name)
                self.error = f"the playlist stopped at {item.name}"
                self.over.set()
        self.started.set()

    def _play(self, item, entry):
        """Shows an item and waits until its time is over. Raises Unplayable or ValueError if it can never be."""
        picture = None
        if not item.is_video:
            try:
                picture = read_quilt(self.playlist.library.path(item), item.name)
            except RuntimeError as error:
                raise Unplayable(str(error)) from error
        try:
            self.display.show_next(self, item, entry, picture)
            self.error = None
        except Unplayable:
            raise
        except RuntimeError as error:  # Not yet: the display tries again by itself.
            self.error = str(error)
        self.started.set()
        while not self.wake.is_set():
            if not item.is_video:
                if self.display.shown_on is not None:
                    self.wake.wait(entry.seconds)
                    return
            else:
                player = self.display.player
                if player is not None and player.ended.wait(POLL_S):
                    if player.broken:
                        raise Unplayable(player.error)
                    return
                if player is not None:
                    continue
            self.wake.wait(POLL_S)
