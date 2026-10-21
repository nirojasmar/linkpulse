import os
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    settings = get_settings()
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return api_key


class ChaosState:
    def __init__(self):
        self.latency_ms: int = 0
        self.error_percent: int = 0
        self.unready: bool = False
        self.hang_healthz: bool = False
        self.memory_buffers: list[bytearray] = []
        self._cpu_threads: list[threading.Thread] = []
        self._cpu_stop_events: list[threading.Event] = []

    def reset(self):
        self.latency_ms = 0
        self.error_percent = 0
        self.unready = False
        self.hang_healthz = False
        self.memory_buffers.clear()
        for stop_event in self._cpu_stop_events:
            stop_event.set()
        self._cpu_threads.clear()
        self._cpu_stop_events.clear()

    def allocate_memory(self, mb: int):
        # 1 MB = 1024 * 1024 bytes
        buffer = bytearray(mb * 1024 * 1024)
        # Touch pages so Linux actually commits the memory
        for i in range(0, len(buffer), 4096):
            buffer[i] = 1
        self.memory_buffers.append(buffer)

    def trigger_cpu_load(self, duration_seconds: int):
        stop_event = threading.Event()
        self._cpu_stop_events.append(stop_event)

        def worker():
            end_time = time.time() + duration_seconds
            while time.time() < end_time and not stop_event.is_set():
                _ = 123456 * 654321

        t = threading.Thread(target=worker, daemon=True)
        self._cpu_threads.append(t)
        t.start()


chaos_state = ChaosState()
router = APIRouter(prefix="/admin/chaos", tags=["chaos"])


def check_chaos_enabled():
    settings = get_settings()
    if not settings.chaos_enabled:
        raise HTTPException(status_code=403, detail="Chaos endpoints are disabled")


@router.post("/latency")
async def inject_latency(
    ms: int = Query(..., ge=0, description="Latency in milliseconds"),
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.latency_ms = ms
    return {"message": f"Injected {ms}ms latency to all requests", "latency_ms": ms}


@router.post("/errors")
async def inject_errors(
    percent: int = Query(..., ge=0, le=100, description="Percentage of requests returning 500"),
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.error_percent = percent
    return {"message": f"Injected {percent}% error rate", "error_percent": percent}


@router.post("/memory")
async def inject_memory(
    mb: int = Query(..., gt=0, description="Megabytes of memory to allocate and hold"),
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.allocate_memory(mb)
    total_held = sum(len(b) for b in chaos_state.memory_buffers) // (1024 * 1024)
    return {"message": f"Allocated {mb}MB memory", "total_allocated_mb": total_held}


@router.post("/cpu")
async def inject_cpu(
    seconds: int = Query(default=60, gt=0, description="Duration in seconds of CPU busy loop"),
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.trigger_cpu_load(seconds)
    return {"message": f"Spawned CPU burner thread for {seconds} seconds"}


@router.post("/unready")
async def inject_unready(
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.unready = True
    return {"message": "/readyz will now return 503 until reset", "unready": True}


@router.post("/hang")
async def inject_hang(
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.hang_healthz = True
    return {"message": "/healthz will now hang or refuse to answer until reset", "hang": True}


@router.post("/crash")
async def inject_crash(
    code: int = Query(default=1, description="Exit code"),
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    # Exit process immediately
    os._exit(code)


@router.delete("")
async def reset_chaos(
    _: str = Depends(require_api_key),
    __: None = Depends(check_chaos_enabled),
):
    chaos_state.reset()
    return {"message": "All chaos faults reset"}
