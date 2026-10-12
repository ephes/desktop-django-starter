from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from dds.config import ConfigError, WrapperConfig, load_wrapper_config, save_wrapper_config


def test_concurrent_saves_use_unique_closed_sibling_files(tmp_path, monkeypatch):
    destination = tmp_path / "config.toml"
    barrier = Barrier(2)
    original_replace = Path.replace
    sources = []
    snapshots = []

    def replace(source, target):
        sources.append(source)
        assert source.parent == destination.parent
        barrier.wait(timeout=5)
        snapshots.append(source.read_text())
        result = original_replace(source, target)
        assert load_wrapper_config(destination) in configs
        return result

    monkeypatch.setattr(Path, "replace", replace)
    configs = [WrapperConfig("codex", "first"), WrapperConfig("pi", "second")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save_wrapper_config, config, destination) for config in configs]
        for future in futures:
            assert future.result(timeout=10) == destination
    assert len(set(sources)) == 2
    assert set(snapshots) == {
        '[wrap]\nharness = "codex"\nmodel = "first"\n',
        '[wrap]\nharness = "pi"\nmodel = "second"\n',
    }
    assert load_wrapper_config(destination) in configs
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_failed_save_cleans_temporary_file(tmp_path, monkeypatch, failure):
    destination = tmp_path / "config.toml"
    save_wrapper_config(WrapperConfig("codex", "original"), destination)
    injected = []

    def fail(*args, **kwargs):
        injected.append(True)
        raise OSError("injected failure")

    if failure == "replace":
        monkeypatch.setattr(Path, "replace", fail)
    else:
        # Both the original Path.write_text and the fixed tempfile writer use io.open.
        import io

        original_open = io.open

        class FailedWriter:
            def __init__(self, stream):
                self.stream = stream

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            write = fail

        def open_writer(file, mode="r", *args, **kwargs):
            stream = original_open(file, mode, *args, **kwargs)
            return FailedWriter(stream) if "w" in mode else stream

        monkeypatch.setattr(io, "open", open_writer)
    with pytest.raises(ConfigError, match="injected failure"):
        save_wrapper_config(WrapperConfig("pi", "replacement"), destination)
    assert injected
    assert load_wrapper_config(destination) == WrapperConfig("codex", "original")
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("'provider\\test'", "provider\\test"),
        ('"provider\\ttest" # inline comment', "provider\ttest"),
        ('"""\nprovider\nmodel"""', "provider\nmodel"),
        ("'''\nprovider\\test\nmodel'''", "provider\\test\nmodel"),
    ],
)
def test_load_toml_strings_preserves_values(tmp_path, value, expected):
    path = tmp_path / "config.toml"
    path.write_text(f'[wrap]\nharness = "codex"\nmodel = {value}\n', encoding="utf-8")
    assert load_wrapper_config(path) == WrapperConfig("codex", expected)


@pytest.mark.parametrize(
    "content",
    [
        '[wrap]\nharness = "pi"\nharness = "codex"\n',
        '[wrap]\nharness = "pi"\n[wrap]\nmodel = "x"\n',
        '[other]\nvalue = invalid\n[wrap]\nharness = "pi"\n',
        'wrap = "pi"\n',
        '[[wrap]]\nharness = "pi"\n',
        "[wrap]\nharness = 1\n",
        '[wrap]\nharness = "pi"\nmodel = 1\n',
        '[wrap]\nharness = "pi"\nmodel = false\n',
        '[wrap]\nharness = "pi"\nmodel = []\n',
        '[wrap]\nharness = "pi"\nmodel = {}\n',
    ],
)
def test_invalid_toml_or_config_types_raise_config_error(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match="config.toml"):
        load_wrapper_config(path)


@pytest.mark.parametrize(
    "model", [None, "", "provider\\test", 'line\nquote"\t', "pony 🦄", "\x00\x1f\x7f"]
)
def test_save_round_trip_is_valid_toml(tmp_path, model):
    from dds.config import tomllib

    path = tmp_path / "config.toml"
    config = WrapperConfig("codex", model)
    save_wrapper_config(config, path)
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert parsed["wrap"].get("model") == (model or None)
    assert load_wrapper_config(path) == WrapperConfig("codex", model or None)


def test_invalid_utf8_raises_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b'[wrap]\nharness = "pi"\nmodel = "\xff"\n')
    with pytest.raises(ConfigError, match="config.toml"):
        load_wrapper_config(path)


def test_unencodable_model_raises_config_error_and_cleans_temp(tmp_path):
    path = tmp_path / "config.toml"
    save_wrapper_config(WrapperConfig("codex", "original"), path)
    with pytest.raises(ConfigError, match="config.toml"):
        save_wrapper_config(WrapperConfig("pi", "a\udc80"), path)
    assert load_wrapper_config(path) == WrapperConfig("codex", "original")
    assert list(tmp_path.iterdir()) == [path]
