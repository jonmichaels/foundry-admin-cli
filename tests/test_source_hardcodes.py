from pathlib import Path


FORBIDDEN_SOURCE_LITERALS = [
    "/home/jon",
    "/home/linuxbrew/.linuxbrew/bin/pm2",
    "noisy.humung.us",
    "/home/jon/projects",
]


def test_source_has_no_local_runtime_hardcodes():
    root = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [literal for literal in FORBIDDEN_SOURCE_LITERALS if literal in text]
        if hits:
            offenders.append(f"{path.relative_to(root.parents[0])}: {hits}")

    assert offenders == []
