"""
library.py  --  Track library with categories & campaign binding
================================================================
Stores metadata in  music_library/library.json.
Audio files are copied into  music_library/ on import.

Data model
----------
Each track:
    {
        "name":        "Tavern of Albius",
        "category":    "Albius",
        "kind":        "ambient",             # "ambient" | "stinger" | "fast_stinger"
        "file":        "tavern_of_albius.ogg",
        "hotkey":      "",                    # e.g. "F1", "1", "q"  (fast_stinger only)
        "campaign_id": "ash_of_gods"          # which campaign this track belongs to ("" = all)
    }

Categories are derived from the tracks themselves -- no separate entity.
"""

import json
import os
import shutil
import logging

logger = logging.getLogger(__name__)

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music_library")
LIB_JSON = os.path.join(LIB_DIR, "library.json")

VALID_KINDS = ("ambient", "stinger", "fast_stinger")


class Track:
    __slots__ = ("name", "category", "kind", "file", "hotkey", "campaign_id")

    def __init__(self, name: str, category: str, kind: str,
                 file: str, hotkey: str = "", campaign_id: str = ""):
        self.name = name
        self.category = category
        self.kind = kind
        self.file = file
        self.hotkey = hotkey
        self.campaign_id = campaign_id

    @property
    def path(self) -> str:
        return os.path.join(LIB_DIR, self.file)

    def to_dict(self) -> dict:
        return {"name": self.name, "category": self.category,
                "kind": self.kind, "file": self.file,
                "hotkey": self.hotkey, "campaign_id": self.campaign_id}

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        return cls(d["name"], d["category"], d["kind"], d["file"],
                   d.get("hotkey", ""), d.get("campaign_id", ""))


class Library:
    """Manages the on-disk track collection."""

    def __init__(self, campaign_id: str = ""):
        os.makedirs(LIB_DIR, exist_ok=True)
        self._all_tracks: list[Track] = []
        self._campaign_id = campaign_id
        self._load()

    @property
    def campaign_id(self) -> str:
        return self._campaign_id

    @campaign_id.setter
    def campaign_id(self, value: str):
        self._campaign_id = value

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self):
        if not os.path.isfile(LIB_JSON):
            return
        with open(LIB_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for d in data:
            t = Track.from_dict(d)
            if os.path.isfile(t.path):
                self._all_tracks.append(t)
            else:
                logger.warning("File missing for '%s', skipping", t.name)
        logger.info("Library loaded: %d tracks", len(self._all_tracks))

    def _save(self):
        with open(LIB_JSON, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in self._all_tracks], f,
                      ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Filtered view (only tracks for current campaign)
    # ------------------------------------------------------------------
    def _filtered(self) -> list[Track]:
        """Return tracks for the current campaign (or all if no campaign set)."""
        if not self._campaign_id:
            return list(self._all_tracks)
        return [t for t in self._all_tracks
                if t.campaign_id == self._campaign_id or t.campaign_id == ""]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_track(self, source_path: str, name: str,
                  category: str, kind: str, hotkey: str = "") -> Track:
        """Import an audio file into the library."""
        if kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {VALID_KINDS}, got '{kind}'")

        ext = os.path.splitext(source_path)[1].lower()
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        safe = safe.strip().replace(" ", "_")
        filename = f"{safe}{ext}"
        dest = os.path.join(LIB_DIR, filename)

        # Copy file into library
        if os.path.abspath(source_path) != os.path.abspath(dest):
            shutil.copy2(source_path, dest)

        track = Track(name=name, category=category, kind=kind,
                      file=filename, hotkey=hotkey,
                      campaign_id=self._campaign_id)
        # Replace if same name exists
        self._all_tracks = [t for t in self._all_tracks if t.name != name]
        self._all_tracks.append(track)
        self._save()
        logger.info("Added %s '%s' [%s] campaign=%s hotkey=%s",
                     kind, name, category, self._campaign_id, hotkey)
        return track

    def update_hotkey(self, name: str, hotkey: str) -> bool:
        for t in self._all_tracks:
            if t.name == name:
                t.hotkey = hotkey
                self._save()
                return True
        return False

    def remove_track(self, name: str) -> bool:
        before = len(self._all_tracks)
        removed = [t for t in self._all_tracks if t.name == name]
        self._all_tracks = [t for t in self._all_tracks if t.name != name]
        if len(self._all_tracks) < before:
            for t in removed:
                try:
                    os.remove(t.path)
                except OSError:
                    pass
            self._save()
            return True
        return False

    def all_tracks(self) -> list[Track]:
        return self._filtered()

    def get_track(self, name: str) -> Track | None:
        for t in self._filtered():
            if t.name == name:
                return t
        return None

    def get_track_by_hotkey(self, hotkey: str) -> Track | None:
        for t in self._filtered():
            if t.hotkey and t.hotkey.lower() == hotkey.lower():
                return t
        return None

    def categories(self, kind: str | None = None) -> list[str]:
        seen = set()
        for t in self._filtered():
            if kind is None or t.kind == kind:
                seen.add(t.category)
        return sorted(seen)

    def tracks_in_category(self, category: str,
                           kind: str | None = None) -> list[Track]:
        result = []
        for t in self._filtered():
            if t.category == category:
                if kind is None or t.kind == kind:
                    result.append(t)
        return result

    def all_fast_stingers(self) -> list[Track]:
        return [t for t in self._filtered() if t.kind == "fast_stinger"]
