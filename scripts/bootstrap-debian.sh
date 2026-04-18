#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  git \
  curl \
  wget \
  unzip \
  zip \
  jq \
  ripgrep \
  fd-find \
  ca-certificates \
  build-essential \
  python3 \
  python3-pip \
  python3-venv \
  python3-dev \
  pipx \
  nodejs \
  npm

python3 --version
pip3 --version
node --version
npm --version
git --version
