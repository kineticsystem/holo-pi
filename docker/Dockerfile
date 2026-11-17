# HoloPi's server, on Debian 13: Python, numpy, Pillow, FastAPI, uvicorn,
# PyAV, libdrm and Mesa's GBM, EGL and OpenGL ES, from Debian's packages,
# built for amd64 and arm64, e.g. a Raspberry Pi 5, and its web page. The
# Python code is not in the image: docker-compose.yml mounts the repo, so that
# a `git pull` and a restart update it. The web page is: a change to web/
# needs ./docker/dock.sh build.

# The web page, built with Node and pnpm in a stage of its own, from the lock
# file: the server's image keeps only its built files, and has no Node.
FROM node:24-slim AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM debian:trixie-slim

# On a Raspberry Pi, arm64, FFmpeg's libraries come from Raspberry Pi's own
# repository, whose build reaches the Pi 5's hardware HEVC decoder: a quilt
# video then decodes about four times faster, with little of the processor.
# Their versions are newer than Debian's, so they replace them; python3-av
# uses them as they are. Elsewhere, Debian's decode on the processor.
# raspberrypi-archive-keyring.pgp is Raspberry Pi OS's copy of their public
# key, from its package raspberrypi-archive-keyring: the copy on their web site
# has SHA-1 signatures, which Debian 13 refuses.
ARG TARGETARCH
COPY --chmod=644 docker/raspberrypi-archive-keyring.pgp /usr/share/keyrings/
RUN if [ "$TARGETARCH" = arm64 ]; then \
      printf 'Types: deb\nURIs: http://archive.raspberrypi.com/debian/\nSuites: trixie\nComponents: main\nSigned-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp\n' \
        > /etc/apt/sources.list.d/raspi.sources; \
    fi

# python3-python-multipart, which FastAPI reads forms with: Debian's
# python3-multipart is another library, of the same module name.

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-numpy python3-pil \
      python3-fastapi python3-uvicorn python3-python-multipart \
      python3-av libavcodec61 \
      libdrm2 libgbm1 libegl1 libgles2 libgl1-mesa-dri mount \
 && rm -rf /var/lib/apt/lists/*

# No __pycache__ in the mounted repo, which is read-only, and the log at once.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# The tables of the interleaving, next to the last quilt, in the volume of
# docker-compose.yml: a restart reuses them.
ENV XDG_CACHE_HOME=/var/lib/holo-pi/cache
# The web page, which the server serves on /, and Swagger UI's files, for its
# documentation on /api/docs.
COPY --from=web /web/dist /opt/holo-pi/web
ENV HOLO_PI_WEB=/opt/holo-pi/web

WORKDIR /holo-pi
