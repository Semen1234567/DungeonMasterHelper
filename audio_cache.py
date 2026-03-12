import hashlib
import logging
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

PREVIEW_SECONDS = 20
CACHE_DIR_NAME = ".audio_cache"
CACHE_SAMPLE_RATE = 44100
CACHE_CHANNELS = 2
CACHE_CODEC = "pcm_s16le"


@dataclass(frozen=True)
class AudioCachePaths:
    source_path: str
    full_wav_path: str
    preview_wav_path: str


def get_audio_cache_paths(source_path: str) -> AudioCachePaths:
    source_abs = os.path.abspath(source_path)
    source_dir = os.path.dirname(source_abs)
    cache_dir = os.path.join(source_dir, CACHE_DIR_NAME)
    os.makedirs(cache_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(source_abs))[0]
    digest = hashlib.sha1(source_abs.encode("utf-8")).hexdigest()[:10]
    cache_base = f"{stem}.{digest}"

    return AudioCachePaths(
        source_path=source_abs,
        full_wav_path=os.path.join(cache_dir, f"{cache_base}.full.wav"),
        preview_wav_path=os.path.join(cache_dir, f"{cache_base}.preview.wav"),
    )


def ensure_full_wav(source_path: str) -> str:
    source_abs = os.path.abspath(source_path)
    if os.path.splitext(source_abs)[1].lower() == ".wav":
        return source_abs

    cache_paths = get_audio_cache_paths(source_abs)
    if _is_fresh(source_abs, cache_paths.full_wav_path):
        return cache_paths.full_wav_path

    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        logger.warning("ffmpeg not found, using source file directly for '%s'", source_abs)
        return source_abs

    if _run_ffmpeg(ffmpeg, source_abs, cache_paths.full_wav_path):
        return cache_paths.full_wav_path

    return source_abs


def ensure_preview_wav(source_path: str, seconds: int = PREVIEW_SECONDS) -> str:
    source_abs = os.path.abspath(source_path)
    if seconds <= 0:
        return ensure_full_wav(source_abs)

    cache_paths = get_audio_cache_paths(source_abs)
    if _is_fresh(source_abs, cache_paths.preview_wav_path):
        return cache_paths.preview_wav_path

    if os.path.splitext(source_abs)[1].lower() == ".wav":
        duration = _get_wav_duration(source_abs)
        if duration is not None and duration <= seconds:
            return source_abs
        if _write_wav_preview(source_abs, cache_paths.preview_wav_path, seconds):
            return cache_paths.preview_wav_path

    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        logger.warning("ffmpeg not found, using source file directly for preview '%s'", source_abs)
        return ensure_full_wav(source_abs)

    if _run_ffmpeg(ffmpeg, source_abs, cache_paths.preview_wav_path, seconds=seconds):
        return cache_paths.preview_wav_path

    return ensure_full_wav(source_abs)


def cleanup_cached_audio(source_path: str) -> None:
    cache_paths = get_audio_cache_paths(source_path)
    for cache_file in (cache_paths.preview_wav_path, cache_paths.full_wav_path):
        try:
            os.remove(cache_file)
        except FileNotFoundError:
            pass
        except OSError as ex:
            logger.warning("Could not remove cached audio '%s': %s", cache_file, ex)

    cache_dir = os.path.dirname(cache_paths.full_wav_path)
    try:
        if os.path.isdir(cache_dir) and not os.listdir(cache_dir):
            os.rmdir(cache_dir)
    except OSError:
        pass


def _is_fresh(source_path: str, cache_path: str) -> bool:
    if not os.path.isfile(cache_path):
        return False
    try:
        return os.path.getmtime(cache_path) >= os.path.getmtime(source_path)
    except OSError:
        return False


@lru_cache(maxsize=1)
def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _run_ffmpeg(ffmpeg: str, source_path: str, target_path: str, seconds: int | None = None) -> bool:
    temp_path = f"{target_path}.tmp.wav"
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    command = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-i",
        source_path,
        "-vn",
    ]
    if seconds is not None:
        command.extend(["-t", str(seconds)])
    command.extend(
        [
            "-ac",
            str(CACHE_CHANNELS),
            "-ar",
            str(CACHE_SAMPLE_RATE),
            "-c:a",
            CACHE_CODEC,
            temp_path,
        ]
    )

    try:
        subprocess.run(command, check=True, capture_output=True)
        os.replace(temp_path, target_path)
        return True
    except (OSError, subprocess.CalledProcessError) as ex:
        logger.warning("ffmpeg conversion failed for '%s': %s", source_path, ex)
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return False


def _write_wav_preview(source_path: str, target_path: str, seconds: int) -> bool:
    temp_path = f"{target_path}.tmp.wav"
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    try:
        with wave.open(source_path, "rb") as src:
            frame_count = min(src.getnframes(), int(src.getframerate() * seconds))
            frames = src.readframes(frame_count)
            with wave.open(temp_path, "wb") as dst:
                dst.setnchannels(src.getnchannels())
                dst.setsampwidth(src.getsampwidth())
                dst.setframerate(src.getframerate())
                dst.writeframes(frames)
        os.replace(temp_path, target_path)
        return True
    except (OSError, wave.Error) as ex:
        logger.warning("Could not create WAV preview for '%s': %s", source_path, ex)
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return False


def _get_wav_duration(source_path: str) -> float | None:
    try:
        with wave.open(source_path, "rb") as src:
            rate = src.getframerate()
            if rate <= 0:
                return None
            return src.getnframes() / float(rate)
    except (OSError, wave.Error):
        return None
