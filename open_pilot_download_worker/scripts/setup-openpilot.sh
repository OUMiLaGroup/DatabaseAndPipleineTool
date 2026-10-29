#!/usr/bin/env bash

set -euo pipefail
set -x
export LANG=en_US.UTF-8
export LANGUAGE=en_US:en
export LC_ALL=en_US.UTF-8
export NVIDIA_VISIBLE_DEVICES=all
export NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute
export DEBIAN_FRONTEND=noninteractive

# if [ "$#" -lt 3 ]; then
# 	echo "Usage: $0 <conda_env_name> <run_model_on_cpu_or_not (true or false)> <replace_cereal_service_with_gps_compatible_ceral_serivice_or_not (true or false)>"
# 	exit 1
# fi

# echo "Will use ($1) as environment name"
# conda_env_name="$1"
# run_model_on_cpu="$2"
# replace_cereal_with_gps_cereal="$3"

conda_env_name="${CONDA_ENV_NAME:?CONDA_ENV_NAME environment variable is reuqired}"
run_model_on_cpu="${RUN_MODEL_ON_CPU_OR_NOT:?RUN_MODEL_ON_CPU_OR_NOT environment variable is reuqired}"
replace_cereal_with_gps_cereal="${REPLACE_CEREAL_SERVICE_OR_NOT:?REPLACE_CEREAL_SERVICE_OR_NOT environment variable is reuqired}"


# Install packages
apt-get update
apt-get install -y --no-install-recommends sudo tzdata locales wget file git git-lfs
sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen


if [ "$run_model_on_cpu" = "true" ]; then
	sudo apt update
	sudo apt install -y pocl-opencl-icd
fi


# Install conda
cd ~
apt-get install -y ca-certificates
update-ca-certificates
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash ~/Miniconda3-latest-Linux-x86_64.sh -b
source ~/miniconda3/etc/profile.d/conda.sh
conda tos accept
cd /app

git clone --filter=blob:none --recurse-submodules --also-filter-submodules https://github.com/commaai/openpilot.git
cd openpilot
git checkout v0.9.8
git lfs pull

if [ "$replace_cereal_with_gps_cereal" = "true" ]; then
	cp ../files/cereal_service_with_gps_kalman.py ./cereal/services.py
fi
conda create -n "$conda_env_name" python=3.12 -y
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$conda_env_name"
pip install uv
# Preserve v0.9.8's lockfile. The optional tools extra installs a simulator
# wheel with a mismatched upstream hash; this replay worker does not use it.
python /app/scripts/configure_replay_dependencies.py tools/install_python_dependencies.sh
tools/op.sh setup
source .venv/bin/activate
scons -u -j$(nproc)

# Add extra req
# Add extraction dependencies without re-resolving the entire OpenPilot project
# or removing the dev extras installed above. Preserve OpenPilot's NumPy limit.
uv pip install --python .venv/bin/python pandas opencv-python pyarrow 'numpy<2.0.0'
# Copy over files
cd /app
# ./scripts/copy_over_post_compile_files.sh
