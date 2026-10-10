#!/bin/sh
# Package for Lambda (python3.12, arm64) without Docker: Linux wheels via pip --platform.
set -e
cd "$(dirname "$0")/.."
rm -rf build && mkdir -p build/app/saanjh/assets/pop build/layer/python
cp saanjh/*.py build/app/saanjh/
mkdir -p build/app/site && cp site/index.html site/borders.json site/evidence.json site/districts.json site/api.html site/openapi.yaml build/app/site/
cp data/elevation_crop.npy build/app/saanjh/assets/
cp data/pop/pop_grid.npy build/app/saanjh/assets/pop/
cp saanjh/assets/*.npz saanjh/assets/*.npy build/app/saanjh/assets/  # risk models, farmland mask, last season
.venv/bin/pip install -q --target build/layer/python --platform manylinux2014_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: \
  numpy scipy pandas h5py fsspec aiohttp certifi requests
# boto3 ships with the runtime; trim what Lambda never imports.
# PDF briefings: fpdf2 with fontTools only; Pillow (images) is optional and would push the layer past 250 MB.
.venv/bin/pip install -q --target build/layer/python --no-deps --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 --only-binary=:all: fpdf2 defusedxml fonttools
# numpy 2.x imports from numpy/_core/tests at runtime, so its tests stay.
find build/layer -type d -name __pycache__ -prune -exec rm -rf {} +
find build/layer -type d -name tests -not -path "*/numpy/*" -prune -exec rm -rf {} +
# The assistant's own layer (Strands Agents with its OpenAI-compatible provider for Bedrock Mantle).
mkdir -p build/agent_layer/python
.venv/bin/pip install -q --target build/agent_layer/python --platform manylinux2014_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: "strands-agents[openai]" aws-bedrock-token-generator requests
find build/agent_layer -type d -name __pycache__ -prune -exec rm -rf {} +
du -sh build/app build/layer build/agent_layer
