import asyncio

from viam.robot.client import RobotClient
from viam.logging import getLogger

from speech_service_api import SpeechService

LOGGER = getLogger(__name__)


async def connect():
    opts = RobotClient.Options.with_api_key(
        api_key="<API-Key>", api_key_id="<API-Key-ID>"
    )
    return await RobotClient.at_address("<robot-address>", opts)


async def main():
    machine = await connect()

    LOGGER.info("Resources:")
    LOGGER.info(machine.resource_names)

    tts = SpeechService.from_robot(machine, name="tts")

    LOGGER.info("Preparing to speak...")
    result = await tts.say(text="Hello from the Viam machine!", blocking=True)
    LOGGER.info(f"I think I said:\n {result}")

    # Don't forget to close the machine when you're done!
    await machine.close()


if __name__ == "__main__":
    asyncio.run(main())
