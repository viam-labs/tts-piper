from viam.resource.registry import Registry, ResourceCreatorRegistration

from speech_service_api import SpeechService
from .tts import TtsPiper

Registry.register_resource_creator(
    SpeechService.SUBTYPE,
    TtsPiper.MODEL,
    ResourceCreatorRegistration(TtsPiper.new, TtsPiper.validate_config),
)
