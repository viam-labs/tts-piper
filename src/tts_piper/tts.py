import asyncio
import os
import wave
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import ClassVar, List, Optional, Tuple, cast

import numpy as np
import pyaudio
from piper import PiperVoice
from piper.download_voices import download_voice
from speech_service_api import SpeechService
from typing_extensions import Self
from viam.components.audio_out import AudioOut
from viam.logging import getLogger
from viam.media.audio import AudioCodec
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import AudioInfo, ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.utils import struct_to_dict

LOGGER = getLogger(__name__)

# PortAudio / PyAudio: device rejected the requested sample rate (common on USB DACs).
PA_INVALID_SAMPLE_RATE = -9997
FALLBACK_SAMPLE_RATE = 48000

_SAMPLE_WIDTH_DTYPE = {1: np.int8, 2: np.int16, 4: np.int32}
_APLAY_FORMAT = {1: "U8", 2: "S16_LE", 4: "S32_LE"}


def _is_cuda_available() -> bool:
    """Check if CUDA is available for use with ONNX Runtime."""
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        return "CUDAExecutionProvider" in providers
    except ImportError:
        return False


def _resample_pcm(
    pcm: bytes, sample_width: int, channels: int, from_rate: int, to_rate: int
) -> bytes:
    if from_rate == to_rate:
        return pcm
    dtype = _SAMPLE_WIDTH_DTYPE.get(sample_width)
    if dtype is None:
        raise ValueError(f"Unsupported sample width for resampling: {sample_width}")

    samples = np.frombuffer(pcm, dtype=dtype)
    if channels > 1:
        samples = samples.reshape(-1, channels)
        n_in = samples.shape[0]
        n_out = max(1, int(round(n_in * to_rate / from_rate)))
        x_old = np.linspace(0.0, 1.0, n_in, endpoint=False)
        x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
        out = np.empty((n_out, channels), dtype=dtype)
        for channel in range(channels):
            out[:, channel] = np.interp(x_new, x_old, samples[:, channel]).astype(dtype)
        return out.reshape(-1).tobytes()

    n_in = len(samples)
    n_out = max(1, int(round(n_in * to_rate / from_rate)))
    x_old = np.linspace(0.0, 1.0, n_in, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(dtype).tobytes()


def _list_output_devices(p: pyaudio.PyAudio) -> List[Tuple[int, str]]:
    devices: List[Tuple[int, str]] = []
    for index in range(p.get_device_count()):
        info = p.get_device_info_by_index(index)
        if int(info.get("maxOutputChannels", 0) or 0) <= 0:
            continue
        devices.append((index, str(info.get("name", ""))))
    return devices


def _resolve_device_name(p: pyaudio.PyAudio, device_name: str) -> Optional[int]:
    needle = device_name.lower()
    matches = [
        (index, name)
        for index, name in _list_output_devices(p)
        if needle in name.lower()
    ]
    if not matches:
        available = (
            ", ".join(f"[{i}] {name}" for i, name in _list_output_devices(p))
            or "(none)"
        )
        LOGGER.warning(
            "No PyAudio output device matched device_name %r; falling back to default. "
            "Available outputs: %s",
            device_name,
            available,
        )
        return None

    index, name = matches[0]
    if len(matches) > 1:
        LOGGER.info(
            "Multiple devices matched device_name %r; using first: [%s] %s (also: %s)",
            device_name,
            index,
            name,
            ", ".join(f"[{i}] {n}" for i, n in matches[1:]),
        )
    else:
        LOGGER.info("Matched device_name %r to [%s] %s", device_name, index, name)
    return index


class TtsPiper(SpeechService, EasyResource):
    MODEL: ClassVar[Model] = Model(ModelFamily("viam-labs", "speech"), "tts-piper")

    voice_model_name: str = "en_US-amy-medium"
    sample_rate: Optional[int] = None
    # Preferred local device selectors (see README). device_index is deprecated.
    device_name: Optional[str] = None
    device: Optional[str] = None
    device_index: Optional[int] = None
    audio_out_name: Optional[str] = None
    audio_out: Optional[AudioOut] = None
    data_dir: str = os.environ.get("VIAM_MODULE_DATA", str(Path.cwd()))
    _is_speaking = False

    def __init__(self, name: str) -> None:
        super().__init__(name)

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        tts = cls(config.name)
        tts.reconfigure(config, dependencies)
        return tts

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        attrs = struct_to_dict(config.attributes)
        req_deps: List[str] = []
        audio_out = attrs.get("audio_out")
        if audio_out:
            req_deps.append(str(audio_out))
        return req_deps, []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        attrs = struct_to_dict(config.attributes)
        LOGGER.debug(attrs)
        self.voice_model_name = str(attrs.get("voice_model_name", "en_US-amy-medium"))
        sample_rate = attrs.get("sample_rate")
        self.sample_rate = int(sample_rate) if sample_rate is not None else None

        device_name = attrs.get("device_name")
        self.device_name = str(device_name) if device_name else None
        device = attrs.get("device")
        self.device = str(device) if device else None
        device_index = attrs.get("device_index")
        self.device_index = int(device_index) if device_index is not None else None
        if self.device_index is not None:
            LOGGER.warning(
                "Attribute device_index is deprecated and unstable across USB "
                "re-enumeration; prefer audio_out, device (ALSA PCM), or device_name"
            )

        audio_out_name = attrs.get("audio_out")
        self.audio_out_name = str(audio_out_name) if audio_out_name else None
        self.audio_out = None
        if self.audio_out_name:
            self.audio_out = cast(
                AudioOut,
                dependencies[AudioOut.get_resource_name(self.audio_out_name)],
            )
            LOGGER.info(
                "Playback delegated to audio_out dependency %r", self.audio_out_name
            )

        download_dir = Path(self.data_dir)
        model_path = download_dir / f"{self.voice_model_name}.onnx"
        model_config_path = download_dir / f"{self.voice_model_name}.onnx.json"
        download_voice(self.voice_model_name, download_dir)

        # Use CUDA if available
        use_cuda = _is_cuda_available()
        if use_cuda:
            LOGGER.debug("CUDA detected, enabling GPU acceleration for Piper TTS")
        else:
            LOGGER.debug("CUDA not available, using CPU for Piper TTS")

        self.voice = PiperVoice.load(
            model_path, config_path=model_config_path, use_cuda=use_cuda
        )

    async def close(self):
        LOGGER.info(f"{self.name} is closed.")

    async def is_speaking(self) -> bool:
        return self._is_speaking

    def _output_device_index(self, p: pyaudio.PyAudio) -> Optional[int]:
        if self.device_name:
            return _resolve_device_name(p, self.device_name)
        if self.device_index is not None:
            return self.device_index
        return None

    def _open_playback_stream(
        self,
        p: pyaudio.PyAudio,
        sample_width: int,
        channels: int,
        rate: int,
        output_device_index: Optional[int],
    ) -> pyaudio.Stream:
        open_kwargs = {
            "format": p.get_format_from_width(sample_width),
            "channels": channels,
            "rate": rate,
            "output": True,
        }
        if output_device_index is not None:
            open_kwargs["output_device_index"] = output_device_index
        return p.open(**open_kwargs)

    async def _play_via_audio_out(
        self, pcm: bytes, sample_width: int, channels: int, rate: int
    ) -> None:
        assert self.audio_out is not None
        if sample_width == 2:
            codec = AudioCodec.PCM16
        elif sample_width == 4:
            codec = AudioCodec.PCM32
        else:
            raise ValueError(
                f"audio_out playback requires 16- or 32-bit PCM; got sample_width={sample_width}"
            )
        await self.audio_out.play(
            pcm,
            AudioInfo(codec=codec, sample_rate_hz=rate, num_channels=channels),
        )

    async def _play_via_alsa(
        self, pcm: bytes, sample_width: int, channels: int, rate: int
    ) -> None:
        assert self.device is not None
        aplay_format = _APLAY_FORMAT.get(sample_width)
        if aplay_format is None:
            raise ValueError(
                f"Unsupported sample width for ALSA playback: {sample_width}"
            )

        # plughw:/plug: provide rate conversion; pass native (or configured) rate as-is.
        proc = await asyncio.create_subprocess_exec(
            "aplay",
            "-q",
            "-D",
            self.device,
            "-f",
            aplay_format,
            "-r",
            str(rate),
            "-c",
            str(channels),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate(pcm)
        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"aplay failed for device {self.device!r} (exit {proc.returncode}): {err}"
            )

    async def _play_via_pyaudio(
        self, pcm: bytes, sample_width: int, channels: int, native_rate: int
    ) -> None:
        target_rate = self.sample_rate if self.sample_rate is not None else native_rate
        playback_pcm = _resample_pcm(
            pcm, sample_width, channels, native_rate, target_rate
        )

        p = pyaudio.PyAudio()
        try:
            output_device_index = self._output_device_index(p)
            try:
                stream = self._open_playback_stream(
                    p, sample_width, channels, target_rate, output_device_index
                )
            except OSError as err:
                if (
                    err.errno != PA_INVALID_SAMPLE_RATE
                    or target_rate == FALLBACK_SAMPLE_RATE
                ):
                    raise
                LOGGER.warning(
                    "Sample rate %s rejected by audio device (errno %s); "
                    "retrying at %s Hz with resampling",
                    target_rate,
                    err.errno,
                    FALLBACK_SAMPLE_RATE,
                )
                playback_pcm = _resample_pcm(
                    pcm, sample_width, channels, native_rate, FALLBACK_SAMPLE_RATE
                )
                stream = self._open_playback_stream(
                    p, sample_width, channels, FALLBACK_SAMPLE_RATE, output_device_index
                )

            stream.write(playback_pcm)
            stream.close()
        finally:
            p.terminate()

    async def say(self, text: str, blocking: bool) -> str:
        wav_io, wav_file = self._synthesis(text)
        self._is_speaking = True

        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        native_rate = wav_file.getframerate()
        wav_file.close()

        wav_io.seek(0)
        with wave.open(wav_io, "rb") as reader:
            pcm = reader.readframes(reader.getnframes())

        play_rate = self.sample_rate if self.sample_rate is not None else native_rate
        if self.sample_rate is not None and self.sample_rate != native_rate:
            play_pcm = _resample_pcm(
                pcm, sample_width, channels, native_rate, play_rate
            )
        else:
            play_pcm = pcm

        try:
            if self.audio_out is not None:
                await self._play_via_audio_out(
                    play_pcm, sample_width, channels, play_rate
                )
            elif self.device:
                # ALSA plug devices resample; prefer native rate unless sample_rate is set.
                await self._play_via_alsa(play_pcm, sample_width, channels, play_rate)
            else:
                await self._play_via_pyaudio(pcm, sample_width, channels, native_rate)
        finally:
            self._is_speaking = False

        return text

    async def to_speech(
        self,
        text: str,
    ) -> bytes:
        wav_io, _wav_file = self._synthesis(text)
        return wav_io.getvalue()

    def _synthesis(self, text: str) -> Tuple[BytesIO, wave.Wave_write]:
        wav_io = BytesIO()
        wav_file = wave.open(wav_io, "wb")

        self.voice.synthesize_wav(
            text,
            wav_file,
        )
        return wav_io, wav_file

    async def listen(self) -> str:
        raise NotImplementedError()

    async def listen_trigger(self, type: str) -> Sequence[str]:
        raise NotImplementedError()

    async def completion(self, text: str, blocking: bool) -> str:
        raise NotImplementedError()

    async def to_text(self, speech: bytes, format: str) -> str:
        raise NotImplementedError()

    async def get_commands(self, number: int) -> Sequence[str]:
        raise NotImplementedError()
