from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
import wave
import os
from typing import ClassVar, Tuple
from typing_extensions import Self

from viam.logging import getLogger
from viam.module.module import Reconfigurable
from viam.proto.common import ResourceName
from viam.resource.base import ResourceBase
from viam.proto.app.robot import ComponentConfig
from viam.resource.types import Model, ModelFamily
from viam.utils import struct_to_dict

from speech_service_api import SpeechService
from piper import PiperVoice
from piper.download import ensure_voice_exists, find_voice, get_voices
import pyaudio

LOGGER = getLogger(__name__)


class TtsPiper(SpeechService, Reconfigurable):
    MODEL: ClassVar[Model] = Model(ModelFamily("viam-labs", "speech"), "tts-piper")

    voice_model_name: str = "en_US-amy-medium"
    data_dir: str = os.environ.get("VIAM_MODULE_DATA", str(Path.cwd()))
    _is_speaking = False

    def __init__(self, name: str) -> None:
        super().__init__(name)

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        stt = cls(config.name)
        stt.reconfigure(config, dependencies)
        return stt

    @classmethod
    def validate_config(cls, config: ComponentConfig) -> Sequence[str]:
        return []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        attrs = struct_to_dict(config.attributes)
        LOGGER.debug(attrs)
        self.voice_model_name = str(attrs.get("voice_model_name", "en_US-amy-medium"))
        voices_info = get_voices(self.data_dir, update_voices=True)

        ensure_voice_exists(
            self.voice_model_name, [self.data_dir], self.data_dir, voices_info
        )
        voice_model, voice_config = find_voice(self.voice_model_name, [self.data_dir])

        self.voice = PiperVoice.load(voice_model, config_path=voice_config)

    async def close(self):
        LOGGER.info(f"{self.name} is closed.")

    async def is_speaking(self) -> bool:
        return self._is_speaking

    async def say(self, text: str, blocking: bool) -> str:
        wav_io, wav_file = self._synthesis(text)
        self._is_speaking = True

        p = pyaudio.PyAudio()
        stream = p.open(
            format=p.get_format_from_width(wav_file.getsampwidth()),
            channels=wav_file.getnchannels(),
            rate=wav_file.getframerate(),
            output=True,
        )
        stream.write(wav_io.getvalue())

        stream.close()
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

        self.voice.synthesize(
            text,
            wav_file,
            speaker_id=0,
            sentence_silence=0.0,
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
