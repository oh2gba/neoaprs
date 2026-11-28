"""The workflow of the container image (.github/workflows/container.yml) and its Dockerfile, read as
text: a run that is not the published release's own cannot log in or push; the image is made of the
release's signed .deb; latest is the newest stable release's only."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "container.yml").read_text(encoding="utf-8")
DOCKERFILE = ROOT / "packaging" / "container" / "Dockerfile"
GATE = "if: steps.release.outputs.publish == 'true'"
WRITES = ("docker login", "push=true", "imagetools create", "attest", "digest-")


def job(name: str) -> str:
    """The text of one job, from its key to the next job's."""
    return re.split(r"\n  [\w-]+:\n", WORKFLOW.split(f"\n  {name}:\n", 1)[1], maxsplit=1)[0]


def steps(name: str) -> list[str]:
    """The text of each step of a job."""
    return job(name).split("\n      - ")[1:]


def step(name: str, holding: str) -> str:
    return next(s for s in steps(name) if holding in s)


def test_it_is_started_by_hand_or_by_scripts_release_only_never_by_a_push() -> None:
    on = WORKFLOW.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert re.findall(r"^  (\w+):", on, re.M) == ["workflow_dispatch"] and "required: true" in on
    release = (ROOT / "scripts" / "release").read_text(encoding="utf-8")
    assert '"workflow", "run", CONTAINER_WORKFLOW, "--ref", self.tag, "-f", f"tag={self.tag}"' in release
    assert 'CONTAINER_WORKFLOW = "container.yml"' in release


def test_only_a_run_on_the_tag_of_a_published_release_publishes() -> None:
    gate = step("build", "id: release")
    assert 'if [ "$GITHUB_REF" = "refs/tags/$TAG" ] && [ "$draft" = false ]; then' in gate
    assert gate.count("publish=true") == 1 and "publish=false" in gate.split("if [")[0]
    assert "|| draft=unknown" in gate, "a release the job cannot read is not published"
    for text in steps("build"):
        if any(word in text for word in WRITES):
            assert GATE in text, text[:120]
    assert "    if: needs.build.outputs.publish == 'true'\n" in job("publish")
    assert "\npermissions:\n  contents: read\n\n" in WORKFLOW, "write rights are the jobs' own"


def test_the_image_is_the_releases_signed_package_proven_before_it_is_pushed() -> None:
    fetch = step("build", "signed SHA256SUMS")
    assert "neoaprs_${VERSION}_${{ matrix.arch }}.deb" in fetch and "--pattern SHA256SUMS.sig" in fetch
    assert "scripts/verify-download.py" in fetch
    texts = steps("build")
    proof = next(i for i, t in enumerate(texts) if "scripts/check-container" in t)
    push = next(i for i, t in enumerate(texts) if "push=true" in t)
    assert proof < push
    assert "arch: amd64\n            runner: ubuntu-26.04" in job("build")
    assert "arch: arm64\n            runner: ubuntu-24.04-arm" in job("build")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert '"neoaprs_${version}_amd64.deb" "neoaprs_${version}_arm64.deb"' in release, "the names the release has"


def test_latest_is_the_newest_stable_release_and_a_pre_release_has_its_own_tag_only() -> None:
    tags = step("publish", "id: tags")
    assert re.search(r"\*-\*\) ;;", tags) and 'tags+=(-t "$IMAGE:${VERSION%.*}")' in tags
    assert '[ "$newest" = "$TAG" ] && tags+=(-t "$IMAGE:latest")' in tags
    assert "push-to-registry: true" in step("publish", "attest-build-provenance")
    assert "gh attestation verify" in step("publish", "The attestation holds")


def test_the_dockerfile_installs_the_package_as_a_user_on_the_data_volume_with_the_kind_container() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM debian:\w+-slim@sha256:[0-9a-f]{64}$", text, re.M), "Debian slim, pinned by digest"
    assert "source=neoaprs_${VERSION}_${TARGETARCH}.deb" in text and "COPY" not in text, "no layer keeps the .deb"
    assert "NEOAPRS_CONTAINER=1" in text and "NEOAPRS_DATA_DIR=/data" in text
    assert re.search(r"^USER neoaprs$", text, re.M) and "--uid 1000" in text
    assert 'VOLUME ["/data"]' in text and "EXPOSE 7303" in text and "HEALTHCHECK" in text
    assert 'org.opencontainers.image.source="https://github.com/oh2gba/neoaprs"' in text
