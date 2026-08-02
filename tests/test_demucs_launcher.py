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
