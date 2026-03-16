from pathlib import Path

from poor_cli.command_manifest import load_command_manifest, render_commands_markdown


def test_command_manifest_commands_are_unique():
    manifest = load_command_manifest()
    commands = [command.command for command in manifest.commands]

    assert len(commands) == len(set(commands))
    assert "/task" in commands
    assert "/sandbox" in commands
    assert "/skills" in commands


def test_readme_available_commands_section_matches_manifest():
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    rendered = render_commands_markdown().rstrip("\n")
    contents = readme_path.read_text(encoding="utf-8")
    start = contents.index("## Available Commands")
    tail = contents[start:]
    end_offset = tail.index("\n## Available Tools")
    section = tail[:end_offset].rstrip("\n")

    assert section == rendered
