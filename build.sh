#!/bin/bash
cd `dirname $0`

VIRTUAL_ENV=.venv
SUDO=sudo

export PATH=$PATH:$HOME/.local/bin

if ! command -v $SUDO; then
  echo "no sudo on this system, proceeding as current user"
  SUDO=""
fi

if command -v apt-get; then
  $SUDO apt-get install -qqy portaudio19-dev python3-all-dev python3-pyaudio
else
  echo "Skipping tool installation because your platform is missing apt-get"
  echo "If you see failures below, install the equivalent of python3-venv for your system"
fi

if [ ! "$(command -v uv)" ]; then
  if [ ! "$(command -v curl)" ]; then
    echo "curl is required to install UV. please install curl on this system to continue."
    exit 1
  fi
  echo "Installing uv command"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if command -v brew; then
  brew install portaudio
fi

if ! uv venv --python 3.9 $VIRTUAL_ENV; then
  echo "unable to create required virtual environment"
  exit 1
fi

make clean
make install
make build
make bundle
