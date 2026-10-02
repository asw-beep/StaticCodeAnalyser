from pathlib import Path

from analyzer.discovery import iter_python_files


def _touch(root: Path, *rels: str) -> None:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")


def _rel(root: Path, paths) -> list[str]:
    return [p.relative_to(root).as_posix() for p in paths]


def test_directory_is_walked_recursively_in_sorted_order(tmp_path):
    _touch(tmp_path, "b.py", "a.py", "pkg/c.py", "notes.txt")
    assert _rel(tmp_path, iter_python_files([tmp_path])) == ["a.py", "b.py", "pkg/c.py"]


def test_hidden_cache_and_venv_dirs_are_skipped(tmp_path):
    _touch(tmp_path, "ok.py", ".git/x.py", "__pycache__/y.py", "venv/z.py", "dist/w.py", "foo.egg-info/v.py")
    assert _rel(tmp_path, iter_python_files([tmp_path])) == ["ok.py"]


def test_exclude_matches_names_and_relative_paths(tmp_path):
    _touch(tmp_path, "keep.py", "gen_pb2.py", "tests/fixtures/bad.py", "tests/test_x.py")
    found = _rel(tmp_path, iter_python_files([tmp_path], exclude=["*_pb2.py", "tests/fixtures"]))
    assert found == ["keep.py", "tests/test_x.py"]


def test_explicit_file_is_kept_even_if_excluded_or_not_py(tmp_path):
    _touch(tmp_path, "script", "gen_pb2.py")
    paths = [tmp_path / "script", tmp_path / "gen_pb2.py"]
    assert list(iter_python_files(paths, exclude=["*_pb2.py"])) == paths


def test_missing_path_is_passed_through_for_error_reporting(tmp_path):
    missing = tmp_path / "nope.py"
    assert list(iter_python_files([missing])) == [missing]


def test_duplicates_are_reported_once(tmp_path):
    _touch(tmp_path, "a.py")
    assert len(list(iter_python_files([tmp_path, tmp_path / "a.py"]))) == 1
