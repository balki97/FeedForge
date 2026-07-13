import argparse
import asyncio
import json
import sys
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "htdemucs_6s"
DEFAULT_DEVICE = "auto"
DEFAULT_CONCURRENCY = 1
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7865
ALLOWED_STEMS = {"guitar", "bass", "drums", "vocals", "piano", "other"}
_MODEL_CACHE: dict[str, Any] = {}
_DEVICE_CACHE: dict[str, str] = {}


def create_app(
    storage_dir: Path | None = None,
    *,
    model: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> Any:
    try:
        from fastapi import FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - exercised by CLI startup.
        raise RuntimeError(
            "Demucs server dependencies are not installed. Run: "
            "python -m pip install feedforge[stems]"
        ) from exc

    root = Path(storage_dir or Path(tempfile.gettempdir()) / "feedforge-demucs-server")
    uploads_dir = root / "uploads"
    jobs_dir = root / "jobs"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    separation_slots = asyncio.Semaphore(normalize_concurrency(concurrency))

    app = FastAPI(title="FeedForge Demucs Server")

    @app.get("/health")
    def health() -> dict[str, Any]:
        resolved_device = resolve_device(device)
        return {
            "ok": _demucs_available(),
            "service": "feedforge-demucs-server",
            "model": model,
            "device": resolved_device,
            "requested_device": device,
            "concurrency": normalize_concurrency(concurrency),
            "storage_dir": str(root),
            "accelerators": detect_accelerators(),
            "capabilities": {"separate": True, "pitch": False},
            "demucs_available": _demucs_available(),
        }

    @app.post("/separate")
    async def separate(stems: str = "guitar,bass,drums,vocals,other", file: UploadFile = File(...)) -> dict[str, Any]:
        requested = normalize_stems(stems)
        if not requested:
            raise HTTPException(status_code=400, detail="No supported stems requested.")
        if not _demucs_available():
            raise HTTPException(
                status_code=503,
                detail="Demucs is not installed in this Python environment.",
            )

        job_id = uuid.uuid4().hex
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "song.wav").suffix or ".wav"
        input_path = uploads_dir / f"{job_id}{suffix}"
        input_path.write_bytes(await file.read())

        try:
            async with separation_slots:
                produced = await asyncio.to_thread(run_demucs, input_path, job_dir, requested, model=model, device=device)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return {
            "status": "complete",
            "job_id": job_id,
            "stems": {
                stem: f"/files/{job_id}/{Path(path).name}"
                for stem, path in produced.items()
            },
        }

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job_dir = jobs_dir / _safe_job_id(job_id)
        if not job_dir.is_dir():
            raise HTTPException(status_code=404, detail="Job not found.")
        stems = {
            path.stem: f"/files/{job_id}/{path.name}"
            for path in sorted(job_dir.glob("*"))
            if path.suffix.lower() in {".wav", ".ogg", ".mp3", ".flac", ".opus"}
        }
        return {"status": "complete", "job_id": job_id, "stems": stems}

    @app.delete("/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, Any]:
        safe_id = _safe_job_id(job_id)
        job_dir = jobs_dir / safe_id
        upload_files = list(uploads_dir.glob(f"{safe_id}.*"))
        for path in upload_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if job_dir.is_dir():
            shutil.rmtree(job_dir, ignore_errors=True)
        return {"ok": True, "job_id": safe_id}

    @app.get("/files/{job_id}/{filename}")
    def file_result(job_id: str, filename: str) -> FileResponse:
        job_dir = jobs_dir / _safe_job_id(job_id)
        path = (job_dir / Path(filename).name).resolve()
        try:
            path.relative_to(job_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(path)

    return app


def normalize_stems(value: str | list[str]) -> list[str]:
    raw = value if isinstance(value, list) else str(value).split(",")
    stems: list[str] = []
    for item in raw:
        stem = str(item).strip().lower()
        if stem in ALLOWED_STEMS and stem not in stems:
            stems.append(stem)
    return stems


def normalize_concurrency(value: int | str | None) -> int:
    try:
        parsed = int(value or DEFAULT_CONCURRENCY)
    except (TypeError, ValueError):
        parsed = DEFAULT_CONCURRENCY
    return max(1, min(parsed, 4))


def run_demucs(
    input_path: Path,
    job_dir: Path,
    stems: list[str],
    *,
    model: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
) -> dict[str, Path]:
    input_path = Path(input_path)
    job_dir = Path(job_dir)
    if not stems:
        return {}

    try:
        import soundfile as sf
        import torch
        from demucs.apply import apply_model
        from demucs.audio import convert_audio
    except ImportError as exc:
        raise RuntimeError(f"Demucs runtime dependencies are missing: {exc}") from exc

    resolved_device = resolve_device(device)
    demucs_model = load_demucs_model(model, device=resolved_device)
    data, samplerate = sf.read(input_path, always_2d=True, dtype="float32")
    wav = torch.from_numpy(data.T)
    wav = convert_audio(wav, samplerate, demucs_model.samplerate, demucs_model.audio_channels)

    with torch.no_grad():
        separated = apply_model(
            demucs_model,
            wav[None],
            split=True,
            overlap=0.25,
            progress=False,
            device=resolved_device,
        )[0]

    produced: dict[str, Path] = {}
    source_names = list(getattr(demucs_model, "sources", []))
    for stem in stems:
        if stem not in source_names:
            continue
        target = job_dir / f"{stem}.wav"
        stem_audio = separated[source_names.index(stem)].clamp(-1, 1).cpu().numpy().T
        sf.write(target, stem_audio, demucs_model.samplerate, subtype="PCM_16")
        produced[stem] = target

    if not produced:
        raise RuntimeError("Demucs completed but none of the requested stems were produced.")
    return produced


def load_demucs_model(model: str = DEFAULT_MODEL, *, device: str = DEFAULT_DEVICE) -> Any:
    try:
        from demucs.pretrained import get_model
    except ImportError as exc:
        raise RuntimeError(f"Demucs runtime dependencies are missing: {exc}") from exc

    resolved_device = resolve_device(device)
    cache_key = f"{model}:{resolved_device}"
    demucs_model = _MODEL_CACHE.get(cache_key)
    if demucs_model is None:
        try:
            demucs_model = get_model(model)
        except SystemExit as exc:
            raise RuntimeError(f"Demucs model preload failed for {model}. Check the setup log for missing runtime dependencies.") from exc
        demucs_model.to(resolved_device)
        demucs_model.eval()
        _MODEL_CACHE[cache_key] = demucs_model
    return demucs_model


def resolve_device(requested: str | None = DEFAULT_DEVICE) -> str:
    key = str(requested or DEFAULT_DEVICE).strip().lower()
    if key in _DEVICE_CACHE:
        return _DEVICE_CACHE[key]
    try:
        import torch
    except Exception:  # noqa: BLE001
        _DEVICE_CACHE[key] = "cpu"
        return "cpu"

    if key in {"", "auto"}:
        if torch.cuda.is_available() and torch.cuda.device_count() > 0:
            resolved = "cuda:0"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            resolved = "mps"
        else:
            resolved = "cpu"
    elif key == "cuda":
        resolved = "cuda:0" if torch.cuda.is_available() else "cpu"
    elif key.startswith("cuda"):
        resolved = key if torch.cuda.is_available() else "cpu"
    elif key == "mps":
        resolved = "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
    else:
        resolved = "cpu"

    _DEVICE_CACHE[key] = resolved
    return resolved


def detect_accelerators() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = [{"id": "cpu", "name": "CPU", "kind": "cpu", "available": True}]
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        devices[0]["note"] = f"PyTorch unavailable: {exc}"
        return devices

    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            memory_gb = round(float(getattr(props, "total_memory", 0)) / (1024**3), 1)
            devices.append(
                {
                    "id": f"cuda:{index}",
                    "name": torch.cuda.get_device_name(index),
                    "kind": "cuda",
                    "available": True,
                    "memory_gb": memory_gb,
                }
            )

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        devices.append({"id": "mps", "name": "Apple GPU", "kind": "mps", "available": True})

    return devices


def _find_stem_file(source_dir: Path, stem: str) -> Path | None:
    for suffix in (".wav", ".ogg", ".flac", ".mp3", ".opus"):
        candidate = source_dir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _demucs_available() -> bool:
    try:
        import demucs.separate  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _safe_job_id(value: str) -> str:
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in "-_")
    if not cleaned:
        raise ValueError("Invalid job id.")
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a FeedForge-compatible Demucs stem server.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--storage-dir", type=Path)
    parser.add_argument("--preload-model", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Run: python -m pip install feedforge[stems]",
            file=sys.stderr,
        )
        return 2
    if args.preload_model:
        try:
            load_demucs_model(args.model, device=args.device)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    concurrency = normalize_concurrency(args.concurrency)
    app = create_app(args.storage_dir, model=args.model, device=args.device, concurrency=concurrency)
    print(
        json.dumps(
            {
                "url": f"http://{args.host}:{args.port}",
                "model": args.model,
                "device": resolve_device(args.device),
                "concurrency": concurrency,
                "storage_dir": str(Path(args.storage_dir or Path(tempfile.gettempdir()) / "feedforge-demucs-server")),
            }
        )
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
