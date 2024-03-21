import asyncio

from viam.module.module import Module

from speech_service_api import SpeechService
from . import TtsPiper


async def main():
    module = Module.from_args()
    module.add_model_from_registry(SpeechService.SUBTYPE, TtsPiper.MODEL)
    await module.start()


asyncio.run(main())
