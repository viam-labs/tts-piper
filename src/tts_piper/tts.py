from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
import wave
import os
from typing import ClassVar, Optional, Tuple
from typing_extensions import Self

import numpy as np
from viam.logging import getLogger
from viam.proto.common import ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.proto.app.robot import ComponentConfig
from viam.resource.types import Model, ModelFamily
from viam.utils import struct_to_dict

from speech_service_api import SpeechService
from piper import PiperVoice
from piper.download_voices import download_voice
import pyaudio

LOGGER = getLogger(__name__)

# PortAudio / PyAudio: device rejected the requested sample rate (common on USB DACs).
PA_INVALID_SAMPLE_RATE = -9997
FALLBACK_SAMPLE_RATE = 48000

_SAMPLE_WIDTH_DTYPE = {1: np.int8, 2: np.int16, 4: np.int32}


def _is_cuda_available() -> bool:
    """Check if CUDA is available for use with ONNX Runtime."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        return 'CUDAExecutionProvider' in providers
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


class TtsPiper(SpeechService, EasyResource):
    MODEL: ClassVar[Model] = Model(ModelFamily("viam-labs", "speech"), "tts-piper")

    voice_model_name: str = "en_US-amy-medium"
    sample_rate: Optional[int] = None
    device_index: Optional[int] = None
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
        return [], []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        attrs = struct_to_dict(config.attributes)
        LOGGER.debug(attrs)
        self.voice_model_name = str(attrs.get("voice_model_name", "en_US-amy-medium"))
        sample_rate = attrs.get("sample_rate")
        self.sample_rate = int(sample_rate) if sample_rate is not None else None
        device_index = attrs.get("device_index")
        self.device_index = int(device_index) if device_index is not None else None
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
        
        self.voice = PiperVoice.load(model_path, config_path=model_config_path, use_cuda=use_cuda)

    async def close(self):
        LOGGER.info(f"{self.name} is closed.")

    async def is_speaking(self) -> bool:
        return self._is_speaking

    def _open_playback_stream(
        self,
        p: pyaudio.PyAudio,
        sample_width: int,
        channels: int,
        rate: int,
    ) -> pyaudio.Stream:
        open_kwargs = {
            "format": p.get_format_from_width(sample_width),
            "channels": channels,
            "rate": rate,
            "output": True,
        }
        if self.device_index is not None:
            open_kwargs["output_device_index"] = self.device_index
        return p.open(**open_kwargs)

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

        target_rate = self.sample_rate if self.sample_rate is not None else native_rate
        playback_pcm = _resample_pcm(pcm, sample_width, channels, native_rate, target_rate)

        p = pyaudio.PyAudio()
        try:
            try:
                stream = self._open_playback_stream(p, sample_width, channels, target_rate)
            except OSError as err:
                if err.errno != PA_INVALID_SAMPLE_RATE or target_rate == FALLBACK_SAMPLE_RATE:
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
                    p, sample_width, channels, FALLBACK_SAMPLE_RATE
                )

            stream.write(playback_pcm)
            stream.close()
        finally:
            p.terminate()
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
