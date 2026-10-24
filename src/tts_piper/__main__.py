import asyncio

from viam.module.module import Module

# Imported for its side effect: defining TtsPiper registers the model with the
# registry that run_from_registry serves.
from .tts import TtsPiper  # noqa: F401

if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())
