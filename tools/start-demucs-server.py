from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"FeedForge: running {' '.join(args)}", flush=True)
    return subprocess.run(args, check=check, text=True)


def cuda_ready(python: Path) -> bool:
    probe = (
        "import os,torch;d=os.environ.get('FEEDFORGE_DEMUCS_DEVICE','cuda');"
        "d='cuda' if d=='auto' else d;x=torch.ones(1,device=d);(x+x).cpu();"
        "print(f'FeedForge: CUDA ready - {torch.cuda.get_device_name(torch.device(d))} / "
        "torch {torch.__version__} / CUDA {torch.version.cuda}')"
    )
    return run(str(python), "-c", probe, check=False).returncode == 0


def cuda_torch_index(value: str) -> str:
    if value != "auto":
        return value
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return ""
    result = subprocess.run(
        [nvidia_smi, "--query-gpu=compute_cap", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "https://download.pytorch.org/whl/cu128"
    for line in result.stdout.splitlines():
        try:
            if float(line.strip()) >= 7.5:
                return "https://download.pytorch.org/whl/cu128"
        except ValueError:
            return "https://download.pytorch.org/whl/cu128"
    print("FeedForge: NVIDIA GPU is older than the supported CUDA PyTorch build; using CPU runtime.", flush=True)
    return ""


def sync_install_source(source_root: Path, install_root: Path) -> Path:
    if source_root == install_root:
        return source_root
    target = install_root / "app-src"
    print(f"FeedForge: copying bundled app source to writable folder {target}", flush=True)
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source_root, target)
    return target


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    source_root = script_dir if (script_dir / "pyproject.toml").is_file() else script_dir.parent
    install_root = Path(os.environ.get("FEEDFORGE_DEMUCS_HOME") or source_root).resolve()
    model = os.environ.get("FEEDFORGE_DEMUCS_MODEL") or "htdemucs_6s"
    device = os.environ.get("FEEDFORGE_DEMUCS_DEVICE") or "auto"
    concurrency = os.environ.get("FEEDFORGE_DEMUCS_CONCURRENCY") or "1"
    torch_index = cuda_torch_index(os.environ.get("FEEDFORGE_TORCH_INDEX") or "")

    cache_root = install_root / "model-cache"
    runtime_root = install_root / "runtime"
    temp_root = runtime_root / "temp"
    storage_root = runtime_root / "jobs"
    for folder in (cache_root, temp_root, storage_root):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "TORCH_HOME": str(cache_root / "torch"),
        "XDG_CACHE_HOME": str(cache_root),
        "PIP_CACHE_DIR": str(install_root / "pip-cache"),
        "HF_HOME": str(cache_root / "huggingface"),
        "TEMP": str(temp_root),
        "TMP": str(temp_root),
    })

    venv = install_root / ".demucs-venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    marker = install_root / ".feedforge-stems-source"
    pyproject = source_root / "pyproject.toml"
    stamp = f"{source_root}|pyproject={hashlib.sha256(pyproject.read_bytes()).hexdigest()}|torch={torch_index}|cuda-probe=1"

    print("FeedForge: preparing local stem setup", flush=True)
    print(f"FeedForge: install folder {install_root}", flush=True)
    print(f"FeedForge: selected model {model}", flush=True)
    print(f"FeedForge: selected device {device}", flush=True)

    if not python.is_file():
        print(f"FeedForge: creating local Python environment from {sys.executable}", flush=True)
        run(sys.executable, "-m", "venv", str(venv))
    else:
        print("FeedForge: reusing local Python environment", flush=True)

    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != stamp:
        print("FeedForge: installing FeedForge stem dependencies", flush=True)
        install_source = sync_install_source(source_root, install_root)
        run(str(python), "-m", "pip", "install", "--upgrade", "pip")
        run(str(python), "-m", "pip", "install", "-e", f"{install_source}[stems]")
        if torch_index:
            ready = cuda_ready(python)
            if not ready:
                print("FeedForge: installing CUDA PyTorch runtime", flush=True)
                run(
                    str(python), "-m", "pip", "install", "--upgrade",
                    "torch", "torchvision", "torchaudio", "--index-url", torch_index,
                )
        marker.write_text(stamp, encoding="utf-8")
    else:
        print("FeedForge: dependencies already installed", flush=True)

    if torch_index and not cuda_ready(python):
        if device == "auto":
            print("FeedForge: CUDA runtime cannot execute on this GPU; falling back to CPU.", flush=True)
            device = "cpu"
            os.environ["FEEDFORGE_DEMUCS_DEVICE"] = "cpu"
        else:
            print(
                "FeedForge: the installed CUDA runtime cannot execute on the selected GPU. "
                "Update the NVIDIA driver or select CPU in FeedForge Settings, then start the stem server again. "
                "Open Diagnostics -> Open log for GPU and PyTorch details.",
                file=sys.stderr,
                flush=True,
            )
            return 3

    verify = [str(python), "-c", "import demucs, fastapi, soundfile, torch"]
    if run(*verify, check=False).returncode:
        print("FeedForge: repairing missing stem dependencies", flush=True)
        install_source = sync_install_source(source_root, install_root)
        run(str(python), "-m", "pip", "install", "-e", f"{install_source}[stems]")
        run(*verify)
        marker.write_text(stamp, encoding="utf-8")

    print("FeedForge: starting Demucs server; first launch may download the selected model", flush=True)
    return subprocess.call([
        str(python), "-m", "feedback_converter.demucs_server",
        "--host", "127.0.0.1", "--port", "7865", "--model", model,
        "--device", device, "--concurrency", concurrency,
        "--storage-dir", str(storage_root), "--preload-model",
    ])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
