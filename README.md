# tts-piper

A modular service that provides text-to-speech (TTS) capabilities for machines running on the Viam platform.

This module implements the `say` and `to_text` commands of the [speech service API (`viam-labs:service:speech`)](https://github.com/viam-labs/speech-service-api). Follow the documentation there to learn about how to use it with the Viam SDKs.

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

These are the default values for these fields, none are required to be set for this service.

### Attributes

The following attributes are available for the `viam-labs:speech:speechio` speech service:

| Name    | Type   | Inclusion    | Description |
| ------- | ------ | ------------ | ----------- |
| `voice_model_name` | string | Optional |  The name of the pre-trained [Piper model](https://github.com/rhasspy/piper/blob/master/VOICES.md) to be used. Default: `"en_US-amy-medium"`.  |

[Preview the available models](https://rhasspy.github.io/piper-samples/)

> [!NOTE]
> For more information, see [Configure a Machine](https://docs.viam.com/manage/configuration/).

## Contributing

This project was bootstrapped and it managed by [`rye`](https://rye-up.com/). Follow the documentation for [installing rye](https://rye-up.com/guide/installation/) and then run the `sync` command in your local `git clone` of this project to get started:

```console
git clone https://github.com/viam-labs/tts-piper && cd tts-piper
make install
```

## License: Apache-2.0
