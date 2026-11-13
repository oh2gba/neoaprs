# The machine scripts/check-in-container runs the suite on: what a test can tell of the runner of GitHub's `ubuntu-latest`, so that a test that fails or is skipped there does the same here.
# Ubuntu 24.04 for x86-64 with the system libraries the CI's Linux job installs (.github/workflows/ci.yml, "System libraries of the Qt web engine"), and what the runner has and some tests ask for: git, curl, PHP
# (the server side's tests), a C compiler and make, uv with the Python the workflows name, node 22, and the ordinary user `runner` with uid 1001 (a test of file rights is skipped for root).
# No file of the project is in the image: the script builds it without a build context and unpacks the tree inside the container at each run, so the image changes only when this file does.
#
# uv and node are pinned as the build tools of scripts/build-appimage are: a version and the SHA-256 its makers publish beside the file (the `.sha256` of uv's release on GitHub, node's SHASUMS256.txt).
# The pin is the trust, not the server: a file with another digest fails the build. To move a pin, change the version and the digest together. The Python is the newest of its line that the pinned uv
# knows, checked by uv against the digests it carries.
FROM ubuntu:24.04

ARG UV_VERSION=0.11.26
ARG UV_SHA256=6426a73c3837e6e2483ee344cbc00f36394d179afcba6183cb77437e67db4af0
ARG NODE_VERSION=22.23.3
ARG NODE_SHA256=1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af
ARG PYTHON_VERSION=3.13

# The first line is the CI job's own list of libraries, word for word (tests/test_check_in_container.py compares them). The second is what a runner has before any step: the tools, and the three
# libraries the Qt web engine is linked to that the job's list does not name, because the browsers installed on a runner bring them (without them the import of the web engine fails here).
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      libegl1 libgl1 libnss3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64 libdbus-1-3 libfontconfig1 libxcb-cursor0 libxkbfile1 \
      ca-certificates curl git php-cli build-essential libglib2.0-0t64 libgbm1 libxfixes3 \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/uv.tar.gz "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
 && echo "${UV_SHA256}  /tmp/uv.tar.gz" | sha256sum --check --strict - \
 && tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1 --no-same-owner \
 && rm /tmp/uv.tar.gz \
 && uv --version

RUN curl -fsSL -o /tmp/node.tar.gz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.gz" \
 && echo "${NODE_SHA256}  /tmp/node.tar.gz" | sha256sum --check --strict - \
 && mkdir /opt/node \
 && tar -xzf /tmp/node.tar.gz -C /opt/node --strip-components=1 --no-same-owner \
 && rm /tmp/node.tar.gz \
 && /opt/node/bin/node --version

# UTF-8 as on the runner. UV_PYTHON is what the workflows' setup step says with `python-version`: without it uv would take the newest Python the lock allows. npm asks its registry about nothing but an install.
ENV PATH=/opt/node/bin:$PATH \
    LANG=C.UTF-8 \
    UV_PYTHON=${PYTHON_VERSION} \
    npm_config_update_notifier=false

# The user of a runner's steps, with the two variables a runner's shell has for it (the program asks USER before the password file when it names the user of a service).
RUN groupadd --gid 1001 runner && useradd --uid 1001 --gid 1001 --create-home --shell /bin/bash runner
USER runner
ENV HOME=/home/runner \
    USER=runner

# The folders the script mounts its volumes on (uv's and npm's caches) and the one it unpacks the tree in, made as the runner: a new volume takes the owner of the folder it is first mounted on.
RUN mkdir -p /home/runner/work /home/runner/.cache/uv /home/runner/.npm \
 && uv python install "${PYTHON_VERSION}" \
 && npm --version
WORKDIR /home/runner/work
