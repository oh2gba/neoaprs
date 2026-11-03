"""The install line of the copies before 0.16 (`curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh`, which their update window runs) keeps working: packaging/install.sh.in is the
template the release renders, with the version and the address of the release's wheel, and nothing of it is left unrendered."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "packaging" / "install.sh.in"


def render(version: str, url: str) -> str:
    return TEMPLATE.read_text(encoding="utf-8").replace("@VERSION@", version).replace("@WHEEL_URL@", url)


def test_the_template_renders_to_a_script_with_no_placeholder_left(tmp_path: Path) -> None:
    script = render("9.9.9", "https://github.com/oh2gba/neoaprs/releases/download/v9.9.9/neoaprs-9.9.9-py3-none-any.whl")
    assert not re.search(r"@[A-Z_]+@", script)
    assert 'VERSION="9.9.9"' in script and "neoaprs-9.9.9-py3-none-any.whl" in script
    path = tmp_path / "install.sh"
    path.write_text(script, encoding="utf-8")
    assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0
