from pathlib import Path

from foundry_admin_cli.process import infer_active_world_from_html_title


def test_infer_active_world_from_html_title_matches_world_title(tmp_path: Path):
    worlds_dir = tmp_path / "worlds"
    world_dir = worlds_dir / "module-test-dnd5e"
    world_dir.mkdir(parents=True)
    (world_dir / "world.json").write_text(
        '{"id":"module-test-dnd5e","title":"Module Test DnD5E","system":"dnd5e"}'
    )

    html = """<!doctype html><html><head><title>Module Test DnD5E</title></head></html>"""

    assert infer_active_world_from_html_title(html, worlds_dir) == "module-test-dnd5e"


def test_infer_active_world_from_html_title_returns_none_for_setup_page(tmp_path: Path):
    worlds_dir = tmp_path / "worlds"
    worlds_dir.mkdir()

    html = """<!doctype html><html><head><title>Foundry Virtual Tabletop</title></head></html>"""

    assert infer_active_world_from_html_title(html, worlds_dir) is None
