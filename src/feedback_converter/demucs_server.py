import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "htdemucs_6s"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7865
ALLOWED_STEMS = {"guitar", "bass", "drums", "vocals", "piano", "other"}
_MODEL_CACHE: dict[str, Any] = {}


def create_app(storage_dir: Path | None = None, *, model: str = DEFAULT_MODEL) -> Any:
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

    app = FastAPI(title="FeedForge Demucs Server")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": _demucs_available(),
            "service": "feedforge-demucs-server",
            "model": model,
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
            produced = run_demucs(input_path, job_dir, requested, model=model)
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


def run_demucs(input_path: Path, job_dir: Path, stems: list[str], *, model: str = DEFAULT_MODEL) -> dict[str, Path]:
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

    demucs_model = load_demucs_model(model)
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
            device="cpu",
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


def load_demucs_model(model: str = DEFAULT_MODEL) -> Any:
    try:
        from demucs.pretrained import get_model
    except ImportError as exc:
        raise RuntimeError(f"Demucs runtime dependencies are missing: {exc}") from exc

    demucs_model = _MODEL_CACHE.get(model)
    if demucs_model is None:
        demucs_model = get_model(model)
        demucs_model.cpu()
        demucs_model.eval()
        _MODEL_CACHE[model] = demucs_model
    return demucs_model


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
            load_demucs_model(args.model)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    app = create_app(args.storage_dir, model=args.model)
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.model}))
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
