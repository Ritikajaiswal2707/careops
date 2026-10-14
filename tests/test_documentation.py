from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_readme_documentation_links_exist():
    files = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")), ROOT / "EXPERIMENT_DESIGN.md"]
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    missing = []
    for md_file in files:
        text = md_file.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            local_path = (md_file.parent / path_part).resolve()
            if not local_path.exists():
                missing.append(f"{md_file.relative_to(ROOT)} -> {target}")
    assert not missing, "Missing documentation links:\n" + "\n".join(missing)


def test_readme_clearly_separates_snapshot_api_and_simulation():
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "precomputed synthetic snapshot" in text
    assert "browser-side simulation" in text
    assert "hosted url was not verified" in text


def test_pipeline_snapshot_generation_explicitly_disables_llm_calls():
    source = (ROOT / "model/generate_dashboard_data.py").read_text(encoding="utf-8")
    assert 'extract_intent_hybrid(msg_row["message"], llm_call=None)' in source


def test_github_actions_and_dev_requirements_exist():
    assert (ROOT / ".github/workflows/ci.yml").is_file()
    assert (ROOT / "requirements-dev.txt").is_file()
    assert (ROOT / "docs/TECHNICAL_NOTES.md").is_file()
