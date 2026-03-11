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

All fades run in background threads so the GUI stays responsive.
"""

import os
import threading
import time
import logging

import pygame

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
    load_track(name, path)                -> load a Sound object
    play_ambient(name)                    -> crossfade to ambient loop
    play_stinger(name)                    -> fade out ambient, play stinger alone, restore
    play_fast_stinger(name)               -> instant one-shot, no fade
    stop_all()                            -> fade out everything
    stop_ambient()                        -> fade out ambient only
    stop_stinger()                        -> fade out stinger only (and restore ambient)
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

        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._current_ambient: str | None = None
        self._current_ambient_snd: pygame.mixer.Sound | None = None

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
        self._pending_stinger: pygame.mixer.Sound | None = None

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
    # Track loading
    # ------------------------------------------------------------------
    def load_track(self, name: str, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        snd = pygame.mixer.Sound(path)
        snd.set_volume(1.0)
        with self._lock:
            self._sounds[name] = snd
        logger.info("Loaded '%s' from %s", name, path)

    def unload_track(self, name: str) -> None:
        with self._lock:
            self._sounds.pop(name, None)

    # ------------------------------------------------------------------
    # Ambient playback
    # ------------------------------------------------------------------
    def play_ambient(self, name: str) -> None:
        snd = self._sounds.get(name)
        if snd is None:
            logger.warning("Sound '%s' not loaded", name)
            return

        # Avoid restarting the same ambient when user clicks it again.
        if self._current_ambient == name and self._ch_ambient.get_busy():
            return

        prev_snd = self._current_ambient_snd
        self._current_ambient = name
        self._current_ambient_snd = snd
        threading.Thread(target=self._do_crossfade_ambient,
                         args=(snd, prev_snd), daemon=True).start()

    def _do_crossfade_ambient(self, snd: pygame.mixer.Sound,
                              prev_snd: pygame.mixer.Sound | None = None):
        fade = self._ambient_crossfade

        # Fade out currently playing stinger layers while fading ambient in.
        self._stinger_cancel.set()
        for ch in self._stinger_channels:
            if ch.get_busy():
                ch.fadeout(max(100, min(fade, self._stinger_fade_out)))

        # Ambient -> Ambient overlap: replay current ambient on transition channel
        # and fade it out while the new ambient fades in.
        if self._ch_ambient.get_busy() and prev_snd is not None:
            prev_vol = self._ch_ambient.get_volume()
            if prev_vol > 0.0:
                self._ch_transition.stop()
                self._ch_transition.set_volume(prev_vol)
                self._ch_transition.play(prev_snd, loops=-1)
                threading.Thread(target=self._ramp,
                                 args=(self._ch_transition, prev_vol, 0.0, fade),
                                 daemon=True).start()

        self._ch_ambient.stop()
        self._ch_ambient.set_volume(0.0)
        self._ch_ambient.play(snd, loops=-1)
        self._ramp(self._ch_ambient, 0.0, self._vol_ambient, fade)

    # ------------------------------------------------------------------
    # Stinger playback  (fully replaces ambient while playing)
    # ------------------------------------------------------------------
    def play_stinger(self, name: str) -> None:
        snd = self._sounds.get(name)
        if snd is None:
            logger.warning("Sound '%s' not loaded", name)
            return

        start_worker = False
        with self._lock:
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
            in_ch.fadeout(500)
            threading.Thread(target=self._restore_after_stinger_stop,
                             args=(500,), daemon=True).start()
            return

        # Wait most of stinger duration
        wait = max(0.0, duration - self._stinger_fade_out / 1000.0)
        elapsed = 0.0
        while elapsed < wait:
            if self._stinger_cancel.is_set():
                if self._has_pending_stinger():
                    return
                in_ch.fadeout(500)
                threading.Thread(target=self._restore_after_stinger_stop,
                                 args=(500,), daemon=True).start()
                return
            step = min(0.1, wait - elapsed)
            time.sleep(step)
            elapsed += step

        # Fade current stinger out
        self._ramp(in_ch, in_ch.get_volume(), 0.0, self._stinger_fade_out)
        in_ch.stop()

        self._restore_ambient()

    def _restore_after_stinger_stop(self, fade_ms: int):
        time.sleep(max(0.0, fade_ms) / 1000.0)
        # Wait briefly for channels to actually report idle after fadeout.
        deadline = time.time() + 1.5
        while any(ch.get_busy() for ch in self._stinger_channels) and time.time() < deadline:
            time.sleep(0.05)
        self._force_restore_ambient()

    def _force_restore_ambient(self):
        """Always attempt to bring ambient back after manual stinger stop."""
        if self._current_ambient_snd is None:
            return

        if not self._ch_ambient.get_busy():
            self._ch_ambient.set_volume(0.0)
            self._ch_ambient.play(self._current_ambient_snd, loops=-1)
        self._ramp(self._ch_ambient, self._ch_ambient.get_volume(), self._vol_ambient,
                   self._ambient_restore_in)

    def _restore_ambient(self):
        """Fade ambient back to its normal volume when no stinger remains."""
        if any(ch.get_busy() for ch in self._stinger_channels):
            return
        fade = self._ambient_restore_in
        if self._ch_ambient.get_busy():
            self._ramp(self._ch_ambient, self._ch_ambient.get_volume(), self._vol_ambient, fade)
        elif self._current_ambient_snd is not None:
            self._ch_ambient.set_volume(0.0)
            self._ch_ambient.play(self._current_ambient_snd, loops=-1)
            self._ramp(self._ch_ambient, 0.0, self._vol_ambient, fade)

    # ------------------------------------------------------------------
    # Fast stinger (instant, no fade, no ducking)
    # ------------------------------------------------------------------
    def play_fast_stinger(self, name: str) -> None:
        snd = self._sounds.get(name)
        if snd is None:
            logger.warning("Sound '%s' not loaded", name)
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
        self._ch_ambient.fadeout(fade)
        self._ch_transition.fadeout(fade)
        for ch in self._stinger_channels:
            ch.fadeout(fade)
        for ch in self._fast_channels:
            ch.stop()
        self._current_ambient = None
        self._current_ambient_snd = None

    def stop_ambient(self) -> None:
        """Stop only ambient (stinger keeps playing if active)."""
        self._ch_ambient.fadeout(self._stop_fade)
        self._current_ambient = None
        self._current_ambient_snd = None

    def stop_stinger(self) -> None:
        """Stop stinger early and restore ambient."""
        with self._lock:
            self._pending_stinger = None
        self._stinger_cancel.set()
        for ch in self._stinger_channels:
            ch.fadeout(self._stop_fade)

        # Kick a robust ambient restore path regardless of worker timing.
        threading.Thread(target=self._restore_after_stinger_stop,
                         args=(self._stop_fade,), daemon=True).start()

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
