# The container image of NeoAPRS for Linux hosts (ghcr.io/oh2gba/neoaprs): the release's own .deb
# installed into Debian slim, nothing else built. The .deb brings its CPython, the locked libraries,
# Mercury and Direwolf with their own ALSA library, so the image adds only the CA certificates and
# the time zones. Built by .github/workflows/container.yml from the signed release files, and by
# the release run and CI from a test .deb; scripts/check-container proves an image.
#
#   docker build --build-arg VERSION=0.28.0 -t neoaprs packaging/container   (with the .deb beside this file)
#
# The program runs as the user neoaprs (uid 1000) on the data volume /data; NEOAPRS_CONTAINER=1
# makes it the install kind `container` (docs/manual/install.md). Radios come in by the run
# line: --device for a serial port or /dev/snd, --group-add with the host's group number, or TCP.
# The base is pinned by its digest, which moves with the release routine (docs/MAINTAINING.md).
FROM debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0

ARG VERSION
ARG TARGETARCH

LABEL org.opencontainers.image.title="NeoAPRS" \
      org.opencontainers.image.description="APRS client with a map, messages and a web page, for packet, Mercury HF and LoRa radios" \
      org.opencontainers.image.url="https://neo.oh2gba.eu/" \
      org.opencontainers.image.documentation="https://github.com/oh2gba/neoaprs/blob/master/docs/manual/install.md#docker-linux" \
      org.opencontainers.image.source="https://github.com/oh2gba/neoaprs" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      org.opencontainers.image.vendor="OH2GBA" \
      org.opencontainers.image.version="${VERSION}"

# The .deb is mounted for the install, not copied, so that no layer keeps it. Its postinst asks
# systemd only when there is one; here it says its first-install text.
RUN --mount=type=bind,source=neoaprs_${VERSION}_${TARGETARCH}.deb,target=/tmp/neoaprs.deb \
    set -eu; \
    [ -n "${VERSION}" ] || { echo "VERSION is not given"; exit 1; }; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates tzdata /tmp/neoaprs.deb > /dev/null; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin /var/log/apt /var/log/dpkg.log; \
    useradd --uid 1000 --user-group --home-dir /data --no-create-home --shell /usr/sbin/nologin neoaprs; \
    install -d -o neoaprs -g neoaprs -m 0700 /data; \
    [ "$(neoaprs --version)" = "NeoAPRS ${VERSION}" ]

ENV NEOAPRS_CONTAINER=1 \
    NEOAPRS_DATA_DIR=/data \
    HOME=/data \
    LANG=C.UTF-8

USER neoaprs
WORKDIR /data
VOLUME ["/data"]
EXPOSE 7303

# The page's files need no key; the daemon answers on its own loopback.
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD ["/opt/neoaprs/bin/python3", "-I", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7303/', timeout=8)"]

STOPSIGNAL SIGTERM
ENTRYPOINT ["neoaprs"]
CMD ["run"]
