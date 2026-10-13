# ScanMyLib OCR sandbox image.
#
# The image is deliberately tiny: a Python interpreter, a C compiler (Triton,
# used by vLLM, compiles small launchers at runtime) and a few shared libs.
# The heavy, untrusted dependencies (PaddlePaddle, PaddleOCR, vLLM) and the
# model weights are NOT baked in: the one-shot `ocr-setup` service installs
# them into SANDBOX_DIR, which the `ocr` service then mounts read-only while
# running without any network interface (see compose.yaml).
FROM python:3.12-slim-bookworm

ARG UID=1000
ARG GID=1000

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc libc6-dev libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# uv is only used by the setup container to build the venvs quickly.
RUN pip install --no-cache-dir uv==0.10.9

RUN groupadd -g "${GID}" ocr \
 && useradd -u "${UID}" -g "${GID}" -m -d /home/ocr -s /usr/sbin/nologin ocr \
 && mkdir -p /opt/sandbox /run/scanmylib /var/cache/ocr \
 && chown "${UID}:${GID}" /opt/sandbox /run/scanmylib /var/cache/ocr

COPY setup /app/setup
COPY scanmylib_ocr /app/scanmylib_ocr

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER ${UID}:${GID}
WORKDIR /app
CMD ["python3", "-m", "scanmylib_ocr.supervisor"]
