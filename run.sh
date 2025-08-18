#!/bin/bash
cd `dirname $0`

VIRTUAL_ENV=$VIAM_MODULE_DATA/.venv

export PATH=$PATH:$HOME/.local/bin

source $VIRTUAL_ENV/bin/activate

uv run python -m tts_piper $@
