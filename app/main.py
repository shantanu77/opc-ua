from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas import EventRecord, NamespaceInfo, SimulatorConfig, SimulatorMetrics, SimulatorStatus, StartResponse
from .simulator import OPCUASimulator

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
NAMESPACE_UPLOAD_PATH = BASE_DIR.parent / "uploaded_namespace.xml"

app = FastAPI(title="OPC-UA Traffic Simulator", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
simulator = OPCUASimulator()


@app.on_event("startup")
async def on_startup() -> None:
    simulator._load_nodeset_config()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await simulator.stop()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/simulator/config", response_model=SimulatorConfig)
async def get_config() -> SimulatorConfig:
    return simulator.get_config()


@app.put("/api/simulator/config", response_model=SimulatorConfig)
async def update_config(config: SimulatorConfig) -> SimulatorConfig:
    try:
        await simulator.update_config(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return simulator.get_config()


@app.post("/api/simulator/start", response_model=StartResponse)
async def start_simulator() -> StartResponse:
    try:
        await simulator.start()
    except OSError as exc:
        if "address already in use" in str(exc).lower():
            cfg = simulator.get_config()
            raise HTTPException(
                status_code=409,
                detail=f"Port already in use: {cfg.endpoint}. Another OPC-UA server (e.g. Prosys) may be running on port 4840. Stop it first, or change the endpoint to a free port.",
            ) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StartResponse(success=True, message="Simulator started")


@app.post("/api/simulator/stop", response_model=StartResponse)
async def stop_simulator() -> StartResponse:
    await simulator.stop()
    return StartResponse(success=True, message="Simulator stopped")


@app.get("/api/simulator/status", response_model=SimulatorStatus)
async def status() -> SimulatorStatus:
    return simulator.get_status()


@app.get("/api/simulator/metrics", response_model=SimulatorMetrics)
async def metrics() -> SimulatorMetrics:
    return simulator.get_metrics()


@app.get("/api/simulator/events", response_model=list[EventRecord])
async def events() -> list[EventRecord]:
    return simulator.get_events()


@app.get("/api/namespace/info", response_model=NamespaceInfo)
async def namespace_info() -> NamespaceInfo:
    return NamespaceInfo(**simulator.get_namespace_info())


@app.get("/api/simulator/tags")
async def tags() -> list[dict]:
    return await simulator.get_tags()


@app.post("/api/namespace/upload")
async def upload_namespace_file(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Only .xml files are accepted")
    with NAMESPACE_UPLOAD_PATH.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return {"success": True, "path": str(NAMESPACE_UPLOAD_PATH), "filename": file.filename}


@app.delete("/api/namespace/file")
async def delete_namespace_file() -> dict:
    if NAMESPACE_UPLOAD_PATH.exists():
        NAMESPACE_UPLOAD_PATH.unlink()
    return {"success": True}
