# HoloPi's server, on Debian 13: Python, numpy, Pillow, FastAPI, uvicorn
# and libdrm, all from Debian's packages, built for amd64 and arm64, e.g. a
# Raspberry Pi 5. The code is not in the image: docker-compose.yml mounts the
# repo, so that a `git pull` and a restart update it.

FROM debian:trixie-slim

# python3-python-multipart, which FastAPI reads forms with: Debian's
# python3-multipart is another library, of the same module name.

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-numpy python3-pil \
      python3-fastapi python3-uvicorn python3-python-multipart \
      libdrm2 mount \
 && rm -rf /var/lib/apt/lists/*

# No __pycache__ in the mounted repo, which is read-only, and the log at once.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# The tables of the interleaving, next to the last quilt, in the volume of
# docker-compose.yml: a restart reuses them.
ENV XDG_CACHE_HOME=/var/lib/holo-pi/cache

WORKDIR /holo-pi
