import asyncio

from viam.module.module import Module
from .tts import TtsPiper


if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())
