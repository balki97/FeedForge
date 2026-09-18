from pathlib import Path
from runpy import run_path
from types import SimpleNamespace


def test_cuda_probe_uses_a_real_tensor_operation() -> None:
    launcher = run_path(str(Path(__file__).parents[1] / "tools" / "start-demucs-server.py"))
    cuda_ready = launcher["cuda_ready"]
    commands: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs: object) -> SimpleNamespace:
        commands.append(args)
        return SimpleNamespace(returncode=len(commands) - 1)

    cuda_ready.__globals__["run"] = fake_run

    assert cuda_ready(Path("python"))
    assert not cuda_ready(Path("python"))
    assert "torch.ones(1,device=d)" in commands[0][2]


def test_auto_cuda_runtime_skips_old_nvidia_gpu(monkeypatch) -> None:
    launcher = run_path(str(Path(__file__).parents[1] / "tools" / "start-demucs-server.py"))
    monkeypatch.setattr(launcher["shutil"], "which", lambda _name: "nvidia-smi")
    monkeypatch.setattr(
        launcher["subprocess"],
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="6.1\n"),
    )

    assert launcher["cuda_torch_index"]("auto") == ""


def test_macos_python_candidates_include_homebrew_miniconda(monkeypatch) -> None:
    launcher = run_path(str(Path(__file__).parents[1] / "tools" / "start-demucs-server.py"))
    target = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"
    monkeypatch.setattr(launcher["sys"], "platform", "darwin")
    monkeypatch.setattr(launcher["shutil"], "which", lambda _name: None)
    monkeypatch.setenv("FEEDFORGE_PYTHON_EXE", "")
    monkeypatch.setattr(
        launcher["Path"],
        "is_file",
        lambda self: self.as_posix() == target,
    )

    assert [path.as_posix() for path in launcher["python_candidates"]()] == [target]


def test_auto_device_falls_back_to_cpu_when_cuda_probe_fails(tmp_path, monkeypatch) -> None:
    launcher = run_path(str(Path(__file__).parents[1] / "tools" / "start-demucs-server.py"))
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs: object) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("FEEDFORGE_DEMUCS_HOME", str(tmp_path))
    monkeypatch.setenv("FEEDFORGE_TORCH_INDEX", "https://download.pytorch.org/whl/cu128")
    monkeypatch.setenv("FEEDFORGE_DEMUCS_DEVICE", "auto")
    launcher["main"].__globals__["cuda_ready"] = lambda _python: False
    launcher["main"].__globals__["run"] = fake_run
    monkeypatch.setattr(launcher["subprocess"], "call", lambda args: calls.append(tuple(args)) or 0)
    monkeypatch.setattr(launcher["sys"], "executable", "python")

    assert launcher["main"]() == 0
    assert "--device" in calls[-1]
    assert calls[-1][calls[-1].index("--device") + 1] == "cpu"


def test_packaged_stem_source_is_copied_to_writable_install_folder(tmp_path) -> None:
    launcher = run_path(str(Path(__file__).parents[1] / "tools" / "start-demucs-server.py"))
    source = tmp_path / "read-only-app"
    install = tmp_path / "install"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='feedforge'\n", encoding="utf-8")
    stale = install / "app-src" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")

    copied = launcher["sync_install_source"](source, install)

    assert copied == install / "app-src"
    assert (copied / "pyproject.toml").is_file()
    assert not stale.exists()
    assert launcher["sync_install_source"](source, source) == source
