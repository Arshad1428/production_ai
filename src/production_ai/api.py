import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ConfigDict
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .config import ROOT, Settings
from .guardrails import SYSTEM_PROMPT, check_input, check_output
from .memory import Memory
from .model import OllamaModel
from .observability import Metrics, setup_logging
from .security import principal, admin, RateLimiter

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=32000)
    session_id: UUID | None = None

class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    model: str

class BodyLimit:
    """Bound the actual body, including chunked requests, before JSON parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = scope["app"].state.settings.max_body_bytes
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                return await JSONResponse({"detail":"Request body too large"}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()
        await self.app(scope, replay, send)

def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        config = settings or Settings()
        app.state.settings = config
        app.state.log = setup_logging(ROOT / "logs/service.jsonl", config.log_max_bytes, config.log_backup_count)
        app.state.memory = Memory(ROOT / "data/memory.sqlite3", config.memory_turns, config.memory_ttl_seconds, config.max_sessions)
        app.state.metrics = Metrics()
        app.state.limiter = RateLimiter(config.requests_per_minute)
        app.state.busy = set()
        app.state.active = 0
        async with httpx.AsyncClient(base_url=config.ollama_url.rstrip("/"),
                                     timeout=config.model_timeout_seconds, trust_env=False) as client:
            app.state.model = OllamaModel(client, config)
            app.state.log.info("service_started")
            yield
        app.state.log.info("service_stopped")

    app = FastAPI(title="Production AI Service", version="1.0.0", lifespan=lifespan)
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def observe(request, call_next):
        request_id, started = str(uuid4()), time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            # Never log prompts, credentials, bodies, query strings or exception text.
            request.app.state.log.error("request_failed", extra={"fields":{
                "request_id":request_id, "error_type":type(exc).__name__}})
            response = JSONResponse({"detail":"Internal service error"}, status_code=500)
        route = request.scope.get("route")
        route = route.path if route else "unmatched"
        elapsed = time.perf_counter()-started
        m = request.app.state.metrics
        m.requests.labels(route, str(status)).inc()
        m.latency.labels(route).observe(elapsed)
        request.app.state.log.info("request_completed", extra={"fields":{
            "request_id":request_id, "route":route, "status":status, "duration_ms":round(elapsed*1000,2)}})
        response.headers.update({"X-Request-ID":request_id, "X-Content-Type-Options":"nosniff", "Cache-Control":"no-store"})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        # FastAPI's default validation details may echo submitted credentials/prompts.
        return JSONResponse({"detail":"Invalid request: check field types, UUID and size limits"}, status_code=422)

    @app.get("/health/live")
    async def live():
        return {"status":"alive"}

    @app.get("/health/ready", dependencies=[Depends(admin)])
    async def ready(request: Request):
        if not await request.app.state.model.ready():
            raise HTTPException(503, "Ollama or configured model is not ready")
        return {"status":"ready", "model":request.app.state.settings.ollama_model}

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request, identity=Depends(principal)):
        state = request.app.state
        state.limiter.check(identity.user_id)
        config = state.settings
        try:
            text = check_input(body.message, config.max_input_chars, config.api_keys)
        except HTTPException:
            state.metrics.blocks.labels("input").inc()
            raise
        session_id = body.session_id or uuid4()
        session = str(session_id)
        lock_key = (identity.user_id, session)
        # Admission checks and reservation have no await, so are atomic in this one-worker service.
        if lock_key in state.busy:
            raise HTTPException(409, "A generation is already in progress for this session")
        if state.active >= config.max_concurrent_generations:
            raise HTTPException(503, "Generation capacity reached", headers={"Retry-After":"5"})
        state.busy.add(lock_key)
        state.active += 1
        state.metrics.active.inc()
        try:
            history = state.memory.read(identity.user_id, session)
            messages = [{"role":"system", "content":SYSTEM_PROMPT}, *history, {"role":"user", "content":text}]
            try:
                answer = await state.model.chat(messages)
            except HTTPException:
                state.metrics.failures.inc()
                raise
            try:
                answer = check_output(answer, config.max_output_chars, config.api_keys)
            except HTTPException:
                state.metrics.blocks.labels("output").inc()
                raise
            state.memory.append(identity.user_id, session, text, answer)
            return ChatResponse(session_id=session_id, answer=answer, model=config.ollama_model)
        finally:
            state.busy.discard(lock_key)
            state.active -= 1
            state.metrics.active.dec()

    @app.delete("/v1/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: UUID, request: Request, identity=Depends(principal)):
        state = request.app.state
        if (identity.user_id, str(session_id)) in state.busy:
            raise HTTPException(409, "Generation in progress; retry deletion after it finishes")
        state.memory.delete(identity.user_id, str(session_id))
        return Response(status_code=204)

    @app.get("/metrics", dependencies=[Depends(admin)])
    async def metrics(request: Request):
        return Response(generate_latest(request.app.state.metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app

app = create_app()
