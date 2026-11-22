# The machine scripts/check-in-container runs the suite on: what a test can tell of the runner that
# packaging/ci/runner.json names, so that a test that fails or is skipped there does the same here.
# Ubuntu for x86-64 in the series of runner.json's `facts`, with the system libraries the CI's Linux
# job installs (.github/workflows/ci.yml, "System libraries of the Qt web engine"), the tools of its
# job `sim`, and what the runner has and some tests ask for: git, curl, PHP (the server side's
# tests), a C compiler and make, uv with the Python the workflows name, node 22, and the ordinary
# user `runner` with uid 1001 (a test of file rights is skipped for root). No file of the project is
# in the image: the script builds it without a build context and unpacks the tree inside the
# container at each run, so the image changes only when this file does.
#
# The runner's Ubuntu is Canonical's cloud image, whose packages are the amd64v3 builds: its gcc
# makes x86-64-v3 code unless told otherwise, and a program built here behaves as one built there
# (Mercury's audio library takes another path of its code under SSE4.2). The image turns the same
# variant on, so it runs only on a processor with x86-64-v3; the script says so before it builds.
# The base is pinned by its digest and the packages by a date of Ubuntu's snapshot service, so the
# same image comes out on every machine and every day. The last RUN of the system stops the build
# when the compiler's version, its default machine or the C library are not runner.json's facts
# (tests/test_check_in_container.py holds the three ARGs to them).
#
# uv and node are pinned as the build tools of scripts/build-appimage are: a version and the SHA-256
# its makers publish beside the file (the `.sha256` of uv's release on GitHub, node's
# SHASUMS256.txt). The pin is the trust, not the server: a file with another digest fails the build.
# To move a pin, change the version and the digest together; the base image's tag and digest move
# together too, and the snapshot date with them (docs/MAINTAINING.md, "When GitHub moves an image").
# The Python is the newest of its line that the pinned uv knows, checked by uv against the digests
# it carries.
# The base's digest as the registry served it at 20261113T184351Z. UBUNTU_SNAPSHOT is that moment or
# later: a package of the base newer than the snapshot's archive would leave the upgrade and the
# install with unmet dependencies (build-essential's libc6-dev asks for the exact libc6).
FROM ubuntu:26.04@sha256:065aa8626841f16057b78b027b464cd59c4fac36c204c72dcbf48d66f5fa8a96

ARG UBUNTU_SNAPSHOT=20261113T184351Z
ARG GCC_MAJOR=15
ARG GCC_MARCH=x86-64-v3
ARG GLIBC=2.43
ARG UV_VERSION=0.11.26
ARG UV_SHA256=6426a73c3837e6e2483ee344cbc00f36394d179afcba6183cb77437e67db4af0
ARG NODE_VERSION=22.23.3
ARG NODE_SHA256=1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af
ARG PYTHON_VERSION=3.13

# apt as the runner has it: the amd64v3 builds of every package (the upgrade swaps the base image's
# own for them) and the phased updates taken at once rather than in Ubuntu's slow rollout. The first
# line of the install is the CI job's own list of libraries, word for word, and the second the job
# `sim`'s tools, word for word (tests/test_check_in_container.py compares both). The third is what a
# runner has before any step: the tools, and the three libraries the Qt web engine is linked to that
# the job's list does not name, because the browsers installed on a runner bring them (without them
# the import of the web engine fails here). The archive's snapshots are served over https only, and
# the base image has no certificates to check that with: they are installed first, from the archive
# as it is today (the one package that is not the snapshot's; it holds no code that runs in a test).
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates \
 && echo 'APT::Architecture-Variants "amd64v3";' > /etc/apt/apt.conf.d/99-variant \
 && echo 'APT::Get::Always-Include-Phased-Updates "true";' > /etc/apt/apt.conf.d/99-phased-updates \
 && apt-get update --snapshot "${UBUNTU_SNAPSHOT}" \
 && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --snapshot "${UBUNTU_SNAPSHOT}" \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --snapshot "${UBUNTU_SNAPSHOT}" \
      libegl1 libgl1 libnss3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64 libdbus-1-3 libfontconfig1 libxcb-cursor0 libxkbfile1 \
      build-essential pkg-config libasound2-dev libasound2-data \
      ca-certificates curl git php-cli libglib2.0-0t64 libgbm1 libxfixes3 \
 && rm -rf /var/lib/apt/lists/*

# The facts of runner.json, or no image.
RUN [ "$(gcc -dumpversion)" = "${GCC_MAJOR}" ] && gcc -Q --help=target | grep -Eq "^\s+-march=\s+${GCC_MARCH}$" && ldd --version | head -n1 | grep -Eq " ${GLIBC}$"

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

# UTF-8 as on the runner. UV_PYTHON is what the workflows' setup step says with `python-version`:
# without it uv would take the newest Python the lock allows. npm asks its registry about nothing
# but an install.
ENV PATH=/opt/node/bin:$PATH \
    LANG=C.UTF-8 \
    UV_PYTHON=${PYTHON_VERSION} \
    npm_config_update_notifier=false

# The user of a runner's steps, with the two variables a runner's shell has for it (the program asks
# USER before the password file when it names the user of a service).
RUN groupadd --gid 1001 runner && useradd --uid 1001 --gid 1001 --create-home --shell /bin/bash runner
USER runner
ENV HOME=/home/runner \
    USER=runner

# The folders the script mounts its volumes on (uv's and npm's caches, and the build cache where
# scripts/build-mercury keeps Mercury's source archive) and the one it unpacks the tree in, made as
# the runner: a new volume takes the owner of the folder it is first mounted on.
RUN mkdir -p /home/runner/work /home/runner/.cache/uv /home/runner/.npm /home/runner/.cache/neoaprs-build \
 && uv python install "${PYTHON_VERSION}" \
 && npm --version
WORKDIR /home/runner/work
