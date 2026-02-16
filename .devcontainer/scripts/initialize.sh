#!/usr/bin/env bash
set -Eeuo pipefail

if [ ! -e $HOME/.local/bin ]; then
  if ! mkdir -p $HOME/.local/bin; then
    echo "Failed to create the ~/.local/bin directory." >&2
    exit 1
  fi
elif [ ! -w $HOME/.local/bin ]; then
  echo "The ~/.local/bin directory is not writable by $USER."
  echo "Please change its owner as root, then retry:"
  echo "sudo chown -R $USER:$USER $HOME/.local/bin"
  exit 1
fi

if [ ! -e $HOME/.zw_devcontainer_slt_cache ]; then
  if ! mkdir $HOME/.zw_devcontainer_slt_cache; then
    echo "Failed to create the DevContainer SLT cache directory." >&2
    exit 1
  fi
elif [ ! -w $HOME/.zw_devcontainer_slt_cache ]; then
  echo "The DevContainer SLT cache directory is not writable by $USER."
  echo "Please change its owner as root, then retry:"
  echo "sudo chown -R $USER:$USER $HOME/.zw_devcontainer_slt_cache"
  exit 1
fi
