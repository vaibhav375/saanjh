#!/bin/sh
# Package for Lambda (python3.12, arm64) without Docker: Linux wheels via pip --platform.
set -e
cd "$(dirname "$0")/.."
rm -rf build && mkdir -p build/app/saanjh/assets/pop build/layer/python
cp saanjh/*.py build/app/saanjh/
mkdir -p build/app/site && cp site/index.html site/borders.json build/app/site/
cp data/elevation_crop.npy build/app/saanjh/assets/
cp data/pop/pop_grid.npy build/app/saanjh/assets/pop/
.venv/bin/pip install -q --target build/layer/python --platform manylinux2014_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: \
  numpy scipy pandas h5py fsspec aiohttp certifi requests
# boto3 ships with the runtime; trim what Lambda never imports.
# numpy 2.x imports from numpy/_core/tests at runtime, so its tests stay.
find build/layer -type d -name __pycache__ -prune -exec rm -rf {} +
find build/layer -type d -name tests -not -path "*/numpy/*" -prune -exec rm -rf {} +
# The assistant's own layer (Strands Agents + a current boto3 for Bedrock Converse).
mkdir -p build/agent_layer/python
.venv/bin/pip install -q --target build/agent_layer/python --platform manylinux2014_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: strands-agents requests
find build/agent_layer -type d -name __pycache__ -prune -exec rm -rf {} +
du -sh build/app build/layer build/agent_layer
