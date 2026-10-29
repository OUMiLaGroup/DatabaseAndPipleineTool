FROM python:3.12-slim

ENV PYTHONPATH=/app/shared:/app

WORKDIR /app

# system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip
RUN pip install --no-cache-dir --upgrade pip

# Shared Python Packages
COPY shared/requirements.txt /app/shared_requirements.txt
RUN pip install --no-cache-dir -r /app/shared_requirements.txt

# cvat_worker packages
COPY cvat_worker/requirements.txt /app/cvat_worker_requirements.txt
RUN pip install --no-cache-dir -r /app/cvat_worker_requirements.txt

# python packages
COPY tests/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY shared /app/shared

# Copy OpenPilot download worker so its functions can be unit tested
COPY open_pilot_download_worker/src /app/open_pilot_download_worker

COPY tests /app

# The error guide, so tests/unit/test_error_guide.py can check every error code is documented
COPY docs /app/docs

WORKDIR /app

CMD ["pytest", "."]
