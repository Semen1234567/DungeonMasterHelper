"""
audio_engine.py  --  D&D Soundboard audio core
================================================
Uses pygame-ce mixer for multi-channel playback.

Logical layers:
  Channel 0    -> Ambient main
  Channels 1-2 -> Stinger pair (allows stinger-to-stinger crossfades)
  Channel 3    -> Transition helper (ambient crossfade overlap)
  Channel 4+   -> Fast stingers

Transition behaviour:
  - Ambient <-> Ambient: overlap during crossfade.
  - Ambient -> Stinger: ambient fades out while stinger fades in.
  - Stinger -> Stinger: outgoing stinger fades out while next fades in.
  - After stinger end/cancel, ambient fades back to target volume.

Tracks are registered on startup, then warmed up in two phases:
preview WAVs first, full WAVs after that. This keeps the campaign window
responsive while still preparing audio for later playback.
All fades run in background threads so the GUI stays responsive.
"""

import os
import threading
import time
import logging

import pygame
from audio_cache import PREVIEW_SECONDS, ensure_full_wav, ensure_preview_wav

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SAMPLE_RATE = 44100
CHANNELS = 2
BUFFER = 2048
FAST_STINGER_CHANNELS = 4  # channels 4..7 for overlapping fast stingers


class MusicEngine:
    """
    Public API
    ----------
    load_track(name, path)                -> register a source track for lazy WAV caching
    prepare_track(name)                   -> background-build preview/full WAV assets for one track
    play_ambient(name)                    -> crossfade to ambient loop
    play_stinger(name)                    -> fade out ambient, play stinger alone, restore
    play_fast_stinger(name)               -> instant one-shot, no fade
    stop_all()                            -> fade out everything
    stop_ambient()                        -> fade out ambient only
    stop_stinger()                        -> fade out stinger only (and restore ambient)
    clear_tracks()                        -> forget all registered tracks
    warmup_tracks(names=None)             -> background-load registered tracks
    cancel_warmup()                       -> cancel the current background warmup
    set_ambient_volume(vol)               -> ambient volume 0.0 .. 1.0
    set_stinger_volume(vol)               -> stinger volume 0.0 .. 1.0
    set_fast_stinger_volume(vol)          -> fast stinger volume 0.0 .. 1.0
    get_current_ambient()                 -> name of current ambient or None
    is_stinger_playing()                  -> bool

    Settings (all in milliseconds unless noted):
    set_ambient_crossfade(ms)
    set_stinger_fade_in(ms)
    set_stinger_fade_out(ms)
    set_ambient_duck_out(ms)
    set_ambient_restore_in(ms)
    set_stop_fade(ms)
    """

    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, -16, CHANNELS, BUFFER)
        pygame.mixer.init()
        total_ch = 4 + FAST_STINGER_CHANNELS
        pygame.mixer.set_num_channels(total_ch)

        self._ch_ambient = pygame.mixer.Channel(0)
        self._stinger_channels = [pygame.mixer.Channel(1), pygame.mixer.Channel(2)]
        self._stinger_idx = 0
        self._ch_transition = pygame.mixer.Channel(3)
        self._fast_channels = [pygame.mixer.Channel(i)
                               for i in range(4, 4 + FAST_STINGER_CHANNELS)]
        self._fast_idx = 0

        self._track_paths: dict[str, str] = {}
        self._preview_sounds: dict[str, pygame.mixer.Sound] = {}
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._current_ambient: str | None = None
        self._current_ambient_snd: pygame.mixer.Sound | None = None
        self._suspended_ambient: str | None = None
        self._suspended_ambient_snd: pygame.mixer.Sound | None = None

        self._vol_ambient: float = 1.0
        self._vol_stinger: float = 1.0
        self._vol_fast: float = 1.0

        # ----- Timing settings (ms) -----
        self._ambient_crossfade: int = 2500
        self._stinger_fade_in: int = 2000
        self._stinger_fade_out: int = 2000
        self._ambient_duck_out: int = 2500
        self._ambient_restore_in: int = 2500
        self._stop_fade: int = 1500

        self._lock = threading.Lock()
        self._stinger_busy = False
        self._stinger_cancel = threading.Event()
        self._stinger_stop_requested = threading.Event()
        self._pending_stinger: pygame.mixer.Sound | None = None
        self._ambient_lock = threading.Lock()
        self._warmup_token = 0
        self._preview_loading: set[str] = set()
        self._full_loading: set[str] = set()

        logger.info("MusicEngine ready  (pygame-ce %s)", pygame.version.ver)

    # ------------------------------------------------------------------
    # Settings getters / setters
    # ------------------------------------------------------------------
    @property
    def ambient_crossfade(self) -> int:
        return self._ambient_crossfade

    def set_ambient_crossfade(self, ms: int) -> None:
        self._ambient_crossfade = max(0, int(ms))

    @property
    def stinger_fade_in(self) -> int:
        return self._stinger_fade_in

    def set_stinger_fade_in(self, ms: int) -> None:
        self._stinger_fade_in = max(0, int(ms))

    @property
    def stinger_fade_out(self) -> int:
        return self._stinger_fade_out

    def set_stinger_fade_out(self, ms: int) -> None:
        self._stinger_fade_out = max(0, int(ms))

    @property
    def ambient_duck_out(self) -> int:
        return self._ambient_duck_out

    def set_ambient_duck_out(self, ms: int) -> None:
        self._ambient_duck_out = max(0, int(ms))

    @property
    def ambient_restore_in(self) -> int:
        return self._ambient_restore_in

    def set_ambient_restore_in(self, ms: int) -> None:
        self._ambient_restore_in = max(0, int(ms))

    @property
    def stop_fade(self) -> int:
        return self._stop_fade

    def set_stop_fade(self, ms: int) -> None:
        self._stop_fade = max(0, int(ms))

    # ------------------------------------------------------------------
    # Track registration / loading
    # ------------------------------------------------------------------
    def load_track(self, name: str, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        with self._lock:
            norm_path = os.path.abspath(path)
            if self._track_paths.get(name) != norm_path:
                self._preview_sounds.pop(name, None)
                self._sounds.pop(name, None)
            self._track_paths[name] = norm_path
        logger.info("Registered '%s' from %s", name, path)

    def unload_track(self, name: str) -> None:
        with self._lock:
            self._track_paths.pop(name, None)
            self._preview_sounds.pop(name, None)
            self._sounds.pop(name, None)

    def clear_tracks(self) -> None:
        self.cancel_warmup()
        with self._lock:
            self._track_paths.clear()
            self._preview_sounds.clear()
            self._sounds.clear()
            self._preview_loading.clear()
            self._full_loading.clear()
        self._current_ambient = None
        self._current_ambient_snd = None
        self._suspended_ambient = None
        self._suspended_ambient_snd = None

    def cancel_warmup(self) -> None:
        with self._lock:
            self._warmup_token += 1

    def warmup_tracks(self, names: list[str] | None = None, delay_ms: int = 0) -> None:
        with self._lock:
            self._warmup_token += 1
            token = self._warmup_token
            if names is None:
                queue = list(self._track_paths)
            else:
                queue = [name for name in names if name in self._track_paths]

        if not queue:
            return

        threading.Thread(
            target=self._warmup_worker,
            args=(token, queue, max(0, int(delay_ms))),
            daemon=True,
        ).start()

    def prepare_track(self, name: str) -> None:
        threading.Thread(
            target=self._prepare_track_worker,
            args=(name,),
            daemon=True,
        ).start()

    def _warmup_worker(self, token: int, queue: list[str], delay_ms: int) -> None:
        if delay_ms > 0:
            remaining = delay_ms / 1000.0
            while remaining > 0:
                if not self._warmup_is_current(token):
                    return
                step = min(0.05, remaining)
                time.sleep(step)
                remaining -= step

        logger.info("Preview warmup started for %d tracks (%ds)", len(queue), PREVIEW_SECONDS)
        preview_loaded = 0
        for name in queue:
            if not self._warmup_is_current(token):
                logger.info("Warmup cancelled during preview phase")
                return
            if self._get_preview_sound(name) is not None:
                preview_loaded += 1
            time.sleep(0.01)

        logger.info("Full WAV warmup started for %d tracks", len(queue))
        full_loaded = 0
        for name in queue:
            if not self._warmup_is_current(token):
                logger.info("Warmup cancelled during full phase")
                return
            if self._get_full_sound(name) is not None:
                full_loaded += 1
            time.sleep(0.01)

        if self._warmup_is_current(token):
            logger.info(
                "Warmup finished: preview=%d/%d full=%d/%d",
                preview_loaded,
                len(queue),
                full_loaded,
                len(queue),
            )

    def _prepare_track_worker(self, name: str) -> None:
        self._get_preview_sound(name)
        self._get_full_sound(name)

    def _warmup_is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._warmup_token

    def _get_preview_sound(self, name: str) -> pygame.mixer.Sound | None:
        return self._get_cached_sound(
            name,
            self._preview_sounds,
            self._preview_loading,
            lambda source_path: ensure_preview_wav(source_path, PREVIEW_SECONDS),
            "preview",
        )

    def _get_full_sound(self, name: str) -> pygame.mixer.Sound | None:
        return self._get_cached_sound(
            name,
            self._sounds,
            self._full_loading,
            ensure_full_wav,
            "full",
        )

    def _get_play_sound(self, name: str) -> pygame.mixer.Sound | None:
        with self._lock:
            snd = self._sounds.get(name)
        if snd is not None:
            return snd
        with self._lock:
            preview = self._preview_sounds.get(name)
        if preview is not None:
            self.prepare_track(name)
            return preview
        preview = self._get_preview_sound(name)
        if preview is not None:
            self.prepare_track(name)
            return preview
        return self._get_full_sound(name)

    def _get_cached_sound(
        self,
        name: str,
        cache: dict[str, pygame.mixer.Sound],
        loading_set: set[str],
        path_builder,
        label: str,
    ) -> pygame.mixer.Sound | None:
        with self._lock:
            snd = cache.get(name)
            source_path = self._track_paths.get(name)
        if snd is not None:
            return snd
        if source_path is None:
            logger.warning("Sound '%s' not registered", name)
            return None

        claimed = False
        while True:
            with self._lock:
                snd = cache.get(name)
                if snd is not None:
                    return snd
                if name not in loading_set:
                    loading_set.add(name)
                    claimed = True
                    break
            time.sleep(0.01)

        try:
            asset_path = path_builder(source_path)
            loaded = pygame.mixer.Sound(asset_path)
            loaded.set_volume(1.0)
            with self._lock:
                existing = cache.get(name)
                current_path = self._track_paths.get(name)
                if existing is not None:
                    return existing
                if current_path == source_path:
                    cache[name] = loaded
                    logger.info("Loaded %s '%s' from %s", label, name, asset_path)
                    return loaded
            return None
        except Exception as ex:
            logger.warning("Could not load %s '%s' from %s: %s", label, name, source_path, ex)
            return None
        finally:
            if claimed:
                with self._lock:
                    loading_set.discard(name)

    # ------------------------------------------------------------------
    # Ambient playback
    # ------------------------------------------------------------------
    def play_ambient(self, name: str) -> None:
        snd = self._get_play_sound(name)
        if snd is None:
            return
        prev_snd = self._current_ambient_snd
        self._current_ambient = name
        self._current_ambient_snd = snd
        self._suspended_ambient = None
        self._suspended_ambient_snd = None
        threading.Thread(target=self._do_crossfade_ambient,
                         args=(snd, prev_snd), daemon=True).start()

    def _do_crossfade_ambient(self, snd: pygame.mixer.Sound,
                              prev_snd: pygame.mixer.Sound | None = None):
        fade = self._ambient_crossfade
        old_ch = self._ch_ambient
        new_ch = self._ch_transition

        # Fade out currently playing stinger layers while fading ambient in.
        self._stinger_cancel.set()
        for ch in self._stinger_channels:
            if ch.get_busy():
                ch.fadeout(max(100, min(fade, self._stinger_fade_out)))

        # Ambient -> Ambient overlap: fade old ambient out while new fades in.
        if old_ch.get_busy() and prev_snd is not None:
            prev_vol = old_ch.get_volume()
            if prev_vol > 0.0:
                new_ch.stop()
                new_ch.set_volume(0.0)
                new_ch.play(snd, loops=-1)
                threading.Thread(target=self._ramp,
                                 args=(old_ch, prev_vol, 0.0, fade),
                                 daemon=True).start()
                self._ramp(new_ch, 0.0, self._vol_ambient, fade)
                old_ch.stop()
                old_ch.set_volume(0.0)
                self._ch_ambient, self._ch_transition = new_ch, old_ch
                return

        # No active ambient yet (or instant switch without overlap).
        old_ch.stop()
        old_ch.set_volume(0.0)
        old_ch.play(snd, loops=-1)
        self._ramp(old_ch, 0.0, self._vol_ambient, fade)

    # ------------------------------------------------------------------
    # Stinger playback  (fully replaces ambient while playing)
    # ------------------------------------------------------------------
    def play_stinger(self, name: str) -> None:
        snd = self._get_play_sound(name)
        if snd is None:
            return

        start_worker = False
        with self._lock:
            if not self._stinger_busy:
                self._suspended_ambient = self._current_ambient
                self._suspended_ambient_snd = self._current_ambient_snd
                self._stinger_stop_requested.clear()
            # Keep only the latest requested stinger to allow quick switching.
            self._pending_stinger = snd
            if self._stinger_busy:
                # Request transition to latest stinger; running worker will switch.
                self._stinger_cancel.set()
                return
            self._stinger_busy = True
            start_worker = True

        if start_worker:
            threading.Thread(target=self._stinger_worker, daemon=True).start()

    def _stinger_worker(self):
        try:
            while True:
                with self._lock:
                    snd = self._pending_stinger
                    self._pending_stinger = None

                if snd is None:
                    return

                self._stinger_cancel.clear()
                self._do_stinger(snd)
        finally:
            with self._lock:
                self._stinger_busy = False

    def _has_pending_stinger(self) -> bool:
        with self._lock:
            return self._pending_stinger is not None

    def _do_stinger(self, snd: pygame.mixer.Sound):
        duration = snd.get_length()

        in_ch = self._stinger_channels[self._stinger_idx % len(self._stinger_channels)]
        out_ch = self._stinger_channels[(self._stinger_idx + 1) % len(self._stinger_channels)]
        self._stinger_idx += 1

        # Ambient -> Stinger overlap
        if self._ch_ambient.get_busy() and self._ch_ambient.get_volume() > 0.0:
            threading.Thread(target=self._ramp,
                             args=(self._ch_ambient, self._ch_ambient.get_volume(), 0.0,
                                   self._ambient_duck_out),
                             daemon=True).start()

        # Stinger -> Stinger overlap
        if out_ch.get_busy() and out_ch.get_volume() > 0.0:
            threading.Thread(target=self._ramp,
                             args=(out_ch, out_ch.get_volume(), 0.0,
                                   self._stinger_fade_out),
                             daemon=True).start()
            out_ch.fadeout(max(100, self._stinger_fade_out))

        # Fade incoming stinger in
        in_ch.stop()
        in_ch.set_volume(0.0)
        in_ch.play(snd, loops=0)
        self._ramp(in_ch, 0.0, self._vol_stinger, self._stinger_fade_in)

        if self._stinger_cancel.is_set():
            # If a new stinger is queued, let next cycle crossfade from this one.
            if self._has_pending_stinger():
                return
            if self._stinger_stop_requested.is_set():
                return
            in_ch.fadeout(500)
            return

        # Wait most of stinger duration
        wait = max(0.0, duration - self._stinger_fade_out / 1000.0)
        elapsed = 0.0
        while elapsed < wait:
            if self._stinger_cancel.is_set():
                if self._has_pending_stinger():
                    return
                if self._stinger_stop_requested.is_set():
                    return
                in_ch.fadeout(500)
                return
            step = min(0.1, wait - elapsed)
            time.sleep(step)
            elapsed += step

        # Crossfade the stinger out against the suspended ambient.
        self._start_ambient_restore()
        self._ramp(in_ch, in_ch.get_volume(), 0.0, self._stinger_fade_out)
        in_ch.stop()

    def _start_ambient_restore(self):
        """Fade the suspended ambient back in, overlapping the stinger fade-out."""
        fade = self._ambient_restore_in
        restore_name = self._current_ambient
        restore_snd = self._current_ambient_snd

        if self._suspended_ambient_snd is not None:
            restore_name = self._suspended_ambient
            restore_snd = self._suspended_ambient_snd

        self._current_ambient = restore_name
        self._current_ambient_snd = restore_snd
        self._suspended_ambient = None
        self._suspended_ambient_snd = None
        self._stinger_stop_requested.clear()

        if self._ch_ambient.get_busy() and restore_snd is not None:
            threading.Thread(
                target=self._ramp,
                args=(self._ch_ambient, self._ch_ambient.get_volume(), self._vol_ambient, fade),
                daemon=True,
            ).start()
        elif restore_snd is not None:
            self._ch_ambient.set_volume(0.0)
            self._ch_ambient.play(restore_snd, loops=-1)
            threading.Thread(
                target=self._ramp,
                args=(self._ch_ambient, 0.0, self._vol_ambient, fade),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    # Fast stinger (instant, no fade, no ducking)
    # ------------------------------------------------------------------
    def play_fast_stinger(self, name: str) -> None:
        snd = self._get_play_sound(name)
        if snd is None:
            return
        ch = self._fast_channels[self._fast_idx % len(self._fast_channels)]
        self._fast_idx += 1
        ch.set_volume(self._vol_fast)
        ch.play(snd, loops=0)
        logger.info("Fast stinger '%s'", name)

    # ------------------------------------------------------------------
    # Volume controls
    # ------------------------------------------------------------------
    def set_ambient_volume(self, vol: float) -> None:
        self._vol_ambient = max(0.0, min(1.0, vol))
        if self._ch_ambient.get_busy() and not self._stinger_busy:
            self._ch_ambient.set_volume(self._vol_ambient)

    def set_stinger_volume(self, vol: float) -> None:
        self._vol_stinger = max(0.0, min(1.0, vol))
        for ch in self._stinger_channels:
            if ch.get_busy():
                ch.set_volume(self._vol_stinger)

    def set_fast_stinger_volume(self, vol: float) -> None:
        self._vol_fast = max(0.0, min(1.0, vol))

    # ------------------------------------------------------------------
    # Stop controls
    # ------------------------------------------------------------------
    def stop_all(self) -> None:
        """Stop everything."""
        fade = self._stop_fade
        self._stinger_cancel.set()
        self._stinger_stop_requested.clear()
        self._ch_ambient.fadeout(fade)
        self._ch_transition.fadeout(fade)
        for ch in self._stinger_channels:
            ch.fadeout(fade)
        for ch in self._fast_channels:
            ch.stop()
        self._current_ambient = None
        self._current_ambient_snd = None
        self._suspended_ambient = None
        self._suspended_ambient_snd = None

    def stop_ambient(self) -> None:
        """Stop only ambient (stinger keeps playing if active)."""
        self._ch_ambient.fadeout(self._stop_fade)
        self._ch_transition.fadeout(self._stop_fade)
        self._current_ambient = None
        self._current_ambient_snd = None
        self._suspended_ambient = None
        self._suspended_ambient_snd = None

    def stop_stinger(self) -> None:
        """Stop stinger early and restore ambient."""
        with self._lock:
            self._pending_stinger = None
        self._stinger_stop_requested.set()
        self._stinger_cancel.set()
        self._start_ambient_restore()
        for ch in self._stinger_channels:
            ch.fadeout(self._stop_fade)

    def get_current_ambient(self) -> str | None:
        return self._current_ambient

    def is_stinger_playing(self) -> bool:
        return self._stinger_busy

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ramp(ch: pygame.mixer.Channel, fr: float, to: float, ms: int):
        steps = max(1, int(ms / 20))  # ~20ms per step for smooth fade
        dt = (ms / 1000.0) / steps
        for i in range(steps + 1):
            t = i / steps
            vol = fr + (to - fr) * t
            ch.set_volume(max(0.0, min(1.0, vol)))
            time.sleep(dt)
        ch.set_volume(max(0.0, min(1.0, to)))
