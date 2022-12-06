#!/usr/bin/env bash

command_exists() {
  command -v "$@" > /dev/null 2>&1
}

if ! command_exists watchmedo; then
  echo "watchmedo (watchdog) is required to run this script"
  echo "Install it with: pip install watchdog"
  exit 1
fi

echo "Watching for changes in: $1"

watchmedo shell-command \
  --recursive \
  --command='echo "Rebuilding..."; python setup.py install' \
  "$1"
