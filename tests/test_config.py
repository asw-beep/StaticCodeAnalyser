import pytest

from analyzer.config import Config, ConfigError, find_config, load_config


def _pyproject(path, body: str):
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_all_keys(tmp_path):
    p = _pyproject(
        tmp_path / "pyproject.toml",
        '[tool.analyzer]\nselect = ["dead-code"]\nignore = ["sql-injection"]\n'
        'exclude = ["build"]\nmin-severity = "warning"\n',
    )
    c = load_config(p)
    assert (c.select, c.ignore, c.exclude, c.min_severity) == (
        ["dead-code"],
        ["sql-injection"],
        ["build"],
        "WARNING",
    )


def test_no_analyzer_table_gives_defaults(tmp_path):
    p = _pyproject(tmp_path / "pyproject.toml", '[project]\nname = "x"\n')
    c = load_config(p)
    assert (c.select, c.ignore, c.min_severity) == (None, [], "INFO")


def test_no_config_path_gives_defaults():
    assert load_config(None) == Config()


@pytest.mark.parametrize(
    "body",
    [
        '[tool.analyzer]\nselct = ["dead-code"]\n',  # typo'd key
        '[tool.analyzer]\nmin-severity = "LOUD"\n',
        '[tool.analyzer]\nignore = "dead-code"\n',  # not a list
        "[tool.analyzer\n",  # invalid TOML
    ],
)
def test_invalid_config_raises(tmp_path, body):
    p = _pyproject(tmp_path / "pyproject.toml", body)
    with pytest.raises(ConfigError):
        load_config(p)


def test_find_config_walks_up_to_nearest_analyzer_table(tmp_path):
    root = _pyproject(tmp_path / "pyproject.toml", '[tool.analyzer]\nignore = ["dead-code"]\n')
    # A nested pyproject WITHOUT [tool.analyzer] (e.g. a sub-package) is skipped.
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    _pyproject(tmp_path / "pkg" / "pyproject.toml", '[project]\nname = "pkg"\n')
    assert find_config(nested) == root.resolve()


def test_find_config_returns_none_when_absent(tmp_path):
    assert find_config(tmp_path) is None
