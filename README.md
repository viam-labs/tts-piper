# tts-piper

A modular service that provides text-to-speech (TTS) capabilities for machines running on the Viam platform.

This module implements the `say` and `to_speech` commands of the [speech service API (`viam-labs:service:speech`)](https://github.com/viam-labs/speech-service-api). Follow the documentation there to learn about how to use it with the Viam SDKs.

## Usage

To use this module, follow these instructions to [add a module from the Viam Registry](https://docs.viam.com/registry/configure/#add-a-modular-resource-from-the-viam-registry) and select the `viam-labs:speech:tts-piper` model from the [`tts-piper` module](https://app.viam.com/module/viam-labs/tts-piper).

### Prerequisites

On Linux:

`run.sh` will automatically install the following system dependencies if not already set up on the machine:

- `python3-pyaudio`
- `portaudio19-dev`

On MacOS, `run.sh` will install the following dependencies before adding the modular resource using [Homebrew](https://brew.sh):

``` bash
brew install portaudio
```

Before configuring your speech service, you must also [create a machine](https://docs.viam.com/fleet/machines/#add-a-new-machine).

## Config

### Viam Service Configuration

Navigate to the **Config** tab of your machine's page in [the Viam app](https://app.viam.com/).
Click on the **Services** subtab and click **Create service**.
Select the `speech` type, then select the `speech:stt-vosk` model.
Click **Add module**, then enter a name for your speech service and click **Create**.

On the new component panel, copy and paste the following attribute template into your service’s **Attributes** box:

```json
{
  "voice_model_name": "en_US-amy-medium"
}
```

Playback device selection (prefer earlier options):

```json
{
  "voice_model_name": "en_US-amy-medium",
  "audio_out": "bspeaker"
}
```

```json
{
  "voice_model_name": "en_US-amy-medium",
  "device": "plughw:CARD=U0x19080x1331,DEV=0"
}
```

```json
{
  "voice_model_name": "en_US-amy-medium",
  "device_name": "USB Device 0x1908",
  "sample_rate": 48000
}
```

None of these fields are required. When unset, playback uses the system default PyAudio output device.

### Attributes

The following attributes are available for the `viam-labs:speech:tts-piper` speech service:

| Name    | Type   | Inclusion    | Description |
| ------- | ------ | ------------ | ----------- |
| `voice_model_name` | string | Optional |  The name of the pre-trained [Piper model](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md) to be used. Default: `"en_US-amy-medium"`.  |
| `audio_out` | string | Optional | Name of an [`audio_out`](https://docs.viam.com/reference/apis/components/audio-out/) component (for example `viam:system-audio:speaker`) to play through. When set, this service synthesizes audio and hands it off; device selection and rate conversion live on that component. Declared as a required dependency. |
| `device` | string | Optional | ALSA PCM string for local playback via `aplay` (for example `"plughw:CARD=U0x19080x1331,DEV=0"`). Prefer `plughw`/`plug` so ALSA handles rate conversion. Ignored when `audio_out` is set. |
| `device_name` | string | Optional | Case-insensitive substring matched against PyAudio output device names at playback time (for example `"USB Device 0x1908"`). Stable across USB re-enumeration; falls back to the default device with a log line if nothing matches. Ignored when `audio_out` or `device` is set. |
| `sample_rate` | int | Optional | Playback sample rate in Hz for local playback. When unset, uses the Piper voice's native rate (often `22050`). On the PyAudio path, if the device rejects that rate (`OSError` `-9997`), playback retries at `48000` with resampling. |
| `device_index` | int | Optional | **Deprecated.** Numeric PyAudio output device index. Unstable across reboots and USB re-enumeration; prefer `audio_out`, `device`, or `device_name`. |

[Preview the available models](https://rhasspy.github.io/piper-samples/)

> [!NOTE]
> For more information, see [Configure a Machine](https://docs.viam.com/manage/configuration/).

## Contributing

This project was bootstrapped and it managed by [`uv`](https://docs.astral.sh/uv/). Follow the documentation for [installing uv](https://docs.astral.sh/uv/getting-started/installation/) and then run the `make install` command in your local `git clone` of this project to get started:

```console
git clone https://github.com/viam-labs/tts-piper && cd tts-piper
make install
```

## License: Apache-2.0
