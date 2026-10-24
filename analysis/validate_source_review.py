"""Verify a clean HEAD archive against a separately supplied private pack.

Usage: python analysis/validate_source_review.py <pack-directory>
Requires Git for this verification only; the checker/tests require no Git.
Writes only temporary derived files under ignored tmp/ and JSON to stdout.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(pack: Path) -> dict[str, str]:
    return {p.relative_to(pack).as_posix(): digest(p.read_bytes())
            for p in sorted(pack.rglob("*")) if p.is_file()}


class AssetCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "img", "link", "iframe", "object", "embed", "source", "video", "audio"}:
            raise AssertionError(f"Report dependency needs review: {tag}")
        if any(key in attributes for key in ("src", "srcset")):
            raise AssertionError(f"Report source needs review: {tag}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    args = parser.parse_args()
    pack = args.pack_dir.resolve()
    assert pack.is_dir(), pack
    before = inventory(pack)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", revision], cwd=ROOT)
    expected = set(tracked.decode().rstrip("\0").split("\0"))
    archive = subprocess.check_output(["git", "archive", "--format=zip", revision], cwd=ROOT)
    required = {"checker.py", "quality_checker/__init__.py", "quality_checker/core.py",
                "quality_checker/config.py", "requirements.txt", "tests/test_checker.py",
                "flags.csv", "diagnostics.csv", "report.html", "README.md",
                "docs/candidate_completion_checklist.md", "docs/step4_validation.md"}
    assert required <= expected, required - expected
    # Exclude the original checkout and site configuration as import helpers.
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in {"PYTHONPATH", "PYTHONHOME"}}
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    commands = []

    def run(arguments: list[str], cwd: Path) -> str:
        result = subprocess.run([sys.executable, *arguments], cwd=cwd, env=environment,
                                text=True, capture_output=True)
        commands.append({"cwd": str(cwd), "argv": [sys.executable, *arguments],
                         "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(json.dumps(commands[-1], indent=2))
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="source review ", dir=scratch) as temporary:
        clean = Path(temporary) / "tracked copy"
        clean.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            members = {item.filename for item in source.infolist() if not item.is_dir()}
            assert members == expected, (members - expected, expected - members)
            for name in members:
                assert not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts
            source.extractall(clean)
        assert not pack.is_relative_to(clean), "Private pack must remain separate"
        imports = set()
        for name in sorted(members):
            if name.endswith(".py"):
                for node in ast.walk(ast.parse((clean / name).read_text(encoding="utf-8"))):
                    if isinstance(node, ast.Import):
                        imports.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                        imports.add(node.module.split(".")[0])
        nonstdlib = imports - sys.stdlib_module_names - {"quality_checker"}
        assert not nonstdlib, sorted(nonstdlib)
        package = run(["-E", "-S", "-c", "import quality_checker; from pathlib import Path; "
                       "p=Path(quality_checker.__file__).resolve(); "
                       "assert p.is_relative_to(Path.cwd()); print(p)"], clean)
        run(["-E", "-S", "-m", "unittest", "discover", "-s", "tests", "-v"], clean)
        reviewed = {name: (clean / name).read_bytes() for name in ("flags.csv", "diagnostics.csv")}
        run(["checker.py", str(pack)], clean)
        for name, content in reviewed.items():
            assert (clean / name).read_bytes() == content, name
            assert (ROOT / name).read_bytes() == content, f"Working reviewed file differs: {name}"
        alternate = Path(temporary) / "alternate output with spaces"
        alternate.mkdir()
        run([str(clean / "checker.py"), str(pack)], alternate)
        for name, content in reviewed.items():
            assert (alternate / name).read_bytes() == content, name
        report = (clean / "report.html").read_text(encoding="utf-8")
        AssetCheck().feed(report)
        assert "url(" not in report.lower() and "@import" not in report.lower()
        report_hash = digest((clean / "report.html").read_bytes())
        assert digest((ROOT / "report.html").read_bytes()) == report_hash
        run(["-E", "-S", "analysis/build_report.py", str(pack)], clean)
        assert digest((clean / "report.html").read_bytes()) == report_hash
        counts = {}
        for name in reviewed:
            with (alternate / name).open(encoding="utf-8", newline="") as handle:
                counts[name] = len(list(csv.DictReader(handle)))
        after = inventory(pack)
        assert before == after, "Private input inventory changed"
        print(json.dumps({"revision": revision, "python": sys.version, "tracked_files": len(members),
                          "package_import": package.strip(), "imports": sorted(imports),
                          "third_party_python_imports": sorted(nonstdlib), "commands": commands,
                          "rows": counts, "output_sha256": {name: digest(data) for name, data in reviewed.items()},
                          "report_sha256": report_hash, "report_rebuild_byte_identical": True,
                          "report_structurally_self_contained": True, "new_visual_verification": False,
                          "input_files_unchanged": len(before), "input_inventory": before}, indent=2))


if __name__ == "__main__":
    main()
