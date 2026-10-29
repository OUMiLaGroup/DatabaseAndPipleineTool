FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV CONDA_ENV_NAME=openpilot
ENV RUN_MODEL_ON_CPU_OR_NOT=true
ENV REPLACE_CEREAL_SERVICE_OR_NOT=true

WORKDIR /app


# Run Setup script
COPY open_pilot_download_worker/scripts/setup-openpilot.sh /app/scripts/setup-openpilot.sh
COPY open_pilot_download_worker/scripts/configure_replay_dependencies.py /app/scripts/configure_replay_dependencies.py
COPY open_pilot_download_worker/files/cereal_service_with_gps_kalman.py /app/files/cereal_service_with_gps_kalman.py

RUN chmod +x /app/scripts/setup-openpilot.sh \
    && /app/scripts/setup-openpilot.sh

# Run jwt script
ARG JWT
COPY open_pilot_download_worker/scripts/register_jwt_docker.sh /app/scripts/register_jwt_docker.sh
RUN chmod +x /app/scripts/register_jwt_docker.sh \
    && /app/scripts/register_jwt_docker.sh "${JWT}"

# Run file copy script
COPY open_pilot_download_worker/files /app/files/
COPY open_pilot_download_worker/scripts/copy_over_post_compile_files.sh /app/scripts/copy_over_post_compile_files.sh
RUN chmod +x /app/scripts/copy_over_post_compile_files.sh \
    && /app/scripts/copy_over_post_compile_files.sh

# instal req
COPY open_pilot_download_worker/scripts/install_requirements.sh /app/scripts/install_requirements.sh
COPY shared/requirements.txt /app/requirements.txt
RUN chmod +x /app/scripts/install_requirements.sh && /app/scripts/install_requirements.sh

WORKDIR /app/src

# Copy Code
COPY open_pilot_download_worker/src /app/src/
COPY shared /app/shared

COPY open_pilot_download_worker/scripts/entrypoint.sh /app/src/entrypoint.sh
RUN chmod +x entrypoint.sh
ENV PYTHONPATH=/app/shared:/app/b
CMD ["./entrypoint.sh"]
