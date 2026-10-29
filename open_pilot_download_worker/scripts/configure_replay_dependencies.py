"""Restrict the pinned OpenPilot installer to this worker's replay use case.

OpenPilot v0.9.8's optional tools extra contains MetaDrive and rerun-sdk.
Neither is used by this project's replay/extraction worker. Keep the upstream
lockfile and hash verification; do not accept a changed simulator wheel hash.
"""

from pathlib import Path
import sys


def configure(installer: Path) -> None:
    original = "uv sync --frozen --all-extras"
    replacement = original + " --no-extra tools"
    text = installer.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines.count(replacement) == 1 and original not in lines:
        return
    if lines.count(original) != 1 or replacement in lines:
        raise ValueError("Unexpected OpenPilot installer; review dependency setup before building")
    lines[lines.index(original)] = replacement
    installer.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    configure(Path(sys.argv[1]))
