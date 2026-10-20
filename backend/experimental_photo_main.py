"""Opt-in V2 real photo bridge. Run separately from the unchanged V1 app.

No engine is configured by default. One child may execute and one request may
wait; neither request IDs nor output directories are reused while work is live.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect

from experimental_photo_transport_v2 import (
    ENGINE_METHODS, MAX_IMAGE_BYTES, MAX_TRANSPORT_BYTES, TransportValidationError,
    UploadedPhoto, validate_transport,
)

MAX_REQUEST_BODY_BYTES = MAX_IMAGE_BYTES + 64 * 1024
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,199}\Z")
EXPECTED_FIELDS = {"image", "request_id", "method", "scope", "strength"}


class PhotoServiceError(Exception):
    def __init__(self, status, code, retryable=False):
        super().__init__(code)
        self.status, self.code, self.retryable = status, code, retryable


def error_response(request_id, status, code, retryable=False):
    # Error text deliberately excludes exception details, arguments and paths.
    messages = {
        "PROCESSOR_UNAVAILABLE": "실험용 AI 처리 모듈이 설정되지 않았습니다.",
        "DUPLICATE_REQUEST_ID": "같은 요청 ID가 처리 중입니다.",
        "PROCESSOR_BUSY": "다른 요청이 처리 중입니다. 잠시 후 다시 시도하세요.",
        "PROCESSOR_TIMEOUT": "AI 처리 제한 시간을 초과했습니다.",
        "INVALID_PROCESSOR_RESULT": "AI 반환 결과를 검증할 수 없습니다.",
        "CLIENT_DISCONNECTED": "요청 연결이 종료되었습니다.",
    }
    return JSONResponse(status_code=status, content={
        "request_id": request_id, "code": code,
        "message": messages.get(code, "요청을 처리할 수 없습니다."), "retryable": retryable,
    })


def positive_timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 3600:
        raise ValueError("Photo timeout must be finite and in (0, 3600].")
    return float(value)


@dataclass(frozen=True)
class PhotoRuntimeConfig:
    python: Path
    bridge: Path
    consumed_registry: Path
    model: Path | None = None
    engines: tuple[str, ...] = ("native_v12",)
    timeout_seconds: float = 600.0
    development_replay: bool = False
    temp_root: Path | None = None
    resident: bool = False

    def __post_init__(self):
        positive_timeout(self.timeout_seconds)
        if type(self.resident) is not bool:
            raise ValueError('Explicit resident boolean required.')
        if type(self.development_replay) is not bool:
            raise ValueError("development_replay must be bool.")
        if (not isinstance(self.engines, tuple) or not self.engines or
                any(type(engine) is not str or engine not in ENGINE_METHODS for engine in self.engines) or
                len(set(self.engines)) != len(self.engines)):
            raise ValueError("Explicit unique supported photo engines are required.")
        for name in ("python", "bridge", "consumed_registry"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_file():
                raise ValueError("Configured photo runtime files must exist.")
            object.__setattr__(self, name, value.resolve(strict=True))
        if self.model is not None:
            if (not isinstance(self.model, Path) or not self.model.is_dir() or
                    not (self.model / "final_config.private.json").is_file() or
                    not (self.model / "final_context_whole_pad.pt").is_file()):
                raise ValueError("Configured model directory must contain config and checkpoint.")
            object.__setattr__(self, "model", self.model.resolve(strict=True))
        if set(self.engines) & {"native_v12", "synthetic_v23"} and self.model is None:
            raise ValueError("Selected engine requires an explicit model.")
        if self.resident and (self.engines != ('synthetic_v23',) or
                not self.bridge.with_name('photo_resident_worker_v29.py').is_file()):
            raise ValueError('Resident runtime requires its explicit synthetic V23 worker.')
        if self.temp_root is not None:
            if not isinstance(self.temp_root, Path) or not self.temp_root.is_dir():
                raise ValueError("Configured temporary root must already exist.")
            object.__setattr__(self, "temp_root", self.temp_root.resolve(strict=True))

    @classmethod
    def from_environment(cls):
        names = ("BLURFING_PHOTO_PYTHON", "BLURFING_PHOTO_BRIDGE", "BLURFING_PHOTO_CONSUMED_REGISTRY")
        values = [os.environ.get(name, "").strip() for name in names]
        if not all(values):
            return None
        try:
            replay = os.environ.get("BLURFING_PHOTO_DEVELOPMENT_REPLAY", "false").strip().lower()
            resident = os.environ.get('BLURFING_PHOTO_RESIDENT','false').strip().lower()
            if replay not in ("true", "false") or resident not in ('true','false'):
                return None
            model = os.environ.get("BLURFING_PHOTO_MODEL", "").strip()
            temp_root = os.environ.get("BLURFING_PHOTO_TEMP_ROOT", "").strip()
            return cls(*(Path(value) for value in values), model=Path(model) if model else None,
                       engines=tuple(os.environ.get("BLURFING_PHOTO_ENGINES", "native_v12").split(",")),
                       timeout_seconds=float(os.environ.get("BLURFING_PHOTO_TIMEOUT_SECONDS", "600")),
                       development_replay=replay == "true", temp_root=Path(temp_root) if temp_root else None,
                       resident=resident=='true')
        except (ValueError, OSError):
            return None


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) < 0 or int(declared) > MAX_REQUEST_BODY_BYTES:
                    raise ValueError
            except ValueError:
                await error_response("", 413, "IMAGE_TOO_LARGE")(scope, receive, send)
                return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BODY_BYTES:
                    raise PhotoServiceError(413, "IMAGE_TOO_LARGE")
            return message

        await self.app(scope, limited_receive, send)


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field.")
        value[key] = item
    return value


async def terminate_child_tree(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                await asyncio.wait_for(killer.wait(), 10)
            except asyncio.TimeoutError:
                killer.kill()
                await killer.wait()
        except OSError:
            # Still terminate the direct child below; mark runtime unhealthy
            # if the process-tree helper is unavailable.
            process.kill()
            await process.wait()
            raise
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await asyncio.wait_for(process.wait(), 10)


class PhotoSubprocessRuntime:
    def __init__(self, config):
        self.config = config
        self._guard = threading.Lock()
        self._inflight = set()
        self._slot = asyncio.Semaphore(1)
        self._unhealthy = False
        self._failed_temporaries = []

    def claim(self, request_id):
        with self._guard:
            if self._unhealthy:
                raise PhotoServiceError(503, "PROCESSOR_UNAVAILABLE", True)
            if request_id in self._inflight:
                raise PhotoServiceError(409, "DUPLICATE_REQUEST_ID")
            if len(self._inflight) >= 2:
                raise PhotoServiceError(429, "PROCESSOR_BUSY", True)
            self._inflight.add(request_id)

    def release(self, request_id):
        with self._guard:
            self._inflight.discard(request_id)

    async def run(self, upload, request_id, engine, deadline):
        acquired = False
        temporary = None
        process = None
        try:
            await asyncio.wait_for(self._slot.acquire(), max(0, deadline - time.monotonic()))
            acquired = True
            if self._unhealthy:
                raise PhotoServiceError(503, "PROCESSOR_UNAVAILABLE", True)
            temporary = tempfile.TemporaryDirectory(prefix="blurfing-photo-v2-", dir=self.config.temp_root)
            root = Path(temporary.name)
            source = root / "input.png"
            source.write_bytes(upload.content)
            # The child creates this fresh directory; it cannot see stale output.
            output = root / "output"
            command = [str(self.config.python), str(self.config.bridge), "--input", str(source),
                       "--output", str(output), "--photo-engine", engine,
                       "--consumed-registry", str(self.config.consumed_registry), "--request-id", request_id]
            if self.config.model is not None and engine in ("native_v12", "synthetic_v23"):
                command.extend(["--photo-model", str(self.config.model)])
            if self.config.development_replay:
                command.append("--development-replay")
            environment = os.environ.copy()
            environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
            options = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
                       getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {"start_new_session": True}
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=self.config.bridge.parent, env=environment, **options))
            try:
                process = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                process = await spawn
                raise
            await asyncio.wait_for(process.wait(), max(0, deadline - time.monotonic()))
            if process.returncode != 0:
                raise PhotoServiceError(500, "PROCESSOR_FAILED", True)
            result = output / "result.transport.json"
            if (output.is_symlink() or output.resolve().parent != root.resolve() or result.is_symlink() or
                    not result.is_file() or result.resolve().parent != output.resolve()):
                raise PhotoServiceError(500, "INVALID_PROCESSOR_RESULT", True)
            # Read an explicit bound even when stat() races with another writer.
            with result.open("rb") as stream:
                content = stream.read(MAX_TRANSPORT_BYTES + 1)
            if len(content) > MAX_TRANSPORT_BYTES:
                raise PhotoServiceError(500, "INVALID_PROCESSOR_RESULT", True)
            payload = json.loads(content, object_pairs_hook=_unique_json_object,
                                 parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Nonfinite JSON.")))
            validated = validate_transport(payload, upload, request_id=request_id, engine=engine)
            if time.monotonic() > deadline:
                raise PhotoServiceError(504, "PROCESSOR_TIMEOUT", True)
            return validated
        except asyncio.TimeoutError as exc:
            raise PhotoServiceError(504, "PROCESSOR_TIMEOUT", True) from exc
        except PhotoServiceError:
            raise
        except Exception as exc:
            raise PhotoServiceError(500, "INVALID_PROCESSOR_RESULT", True) from exc
        finally:
            try:
                if process is not None and process.returncode is None:
                    try:
                        await terminate_child_tree(process)
                    except Exception:
                        self._unhealthy = True
                        if temporary is not None:
                            # Retain private files when tree termination cannot
                            # be confirmed. Never delete beneath a live writer.
                            self._failed_temporaries.append(temporary)
                            temporary = None
                        raise PhotoServiceError(503, "PROCESSOR_UNAVAILABLE", True)
            finally:
                try:
                    if temporary is not None and (process is None or process.returncode is not None):
                        temporary.cleanup()
                finally:
                    if acquired:
                        self._slot.release()


class PhotoResidentRuntime(PhotoSubprocessRuntime):
    """One owned warmed worker; keep admission, validation and cancellation rules."""
    def __init__(self,config):
        super().__init__(config)
        self._process=None;self._start_task=None;self._ready=False;self._closing=False

    @property
    def ready(self):
        return self._ready and self._process is not None and self._process.returncode is None and not self._unhealthy

    def _check_cancelled(self):
        # Python 3.11 wait_for can race completion with outer cancellation.
        # Never let an already requested cancellation proceed to another stage.
        task=asyncio.current_task()
        if task is not None and task.cancelling():raise asyncio.CancelledError()

    async def _frame(self):
        line=await self._process.stdout.readline()
        if not line or len(line)>16384 or not line.endswith(b'\n'):raise ValueError('resident_frame')
        return json.loads(line,object_pairs_hook=_unique_json_object,
            parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_frame')))

    async def _discard(self):
        self._ready=False;process=self._process;self._process=None
        if process is not None:
            try:
                if process.returncode is None:await terminate_child_tree(process)
                else:await process.wait()
            except BaseException:
                self._unhealthy=True;raise
            finally:
                if process.stdin is not None:process.stdin.close()

    async def _spawn(self):
        command=[str(self.config.python),str(self.config.bridge.with_name('photo_resident_worker_v29.py')),
            '--model',str(self.config.model),'--registry',str(self.config.consumed_registry)]
        if self.config.development_replay:command.append('--development-replay')
        options=({'creationflags':getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)|getattr(subprocess,'CREATE_NO_WINDOW',0)}
            if os.name=='nt' else {'start_new_session':True})
        environment=os.environ.copy();environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
        spawn=asyncio.create_task(asyncio.create_subprocess_exec(*command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,limit=16384,cwd=self.config.bridge.parent,env=environment,**options))
        try:
            try:self._process=await asyncio.shield(spawn)
            except asyncio.CancelledError:
                self._process=await spawn;raise
            if await asyncio.wait_for(self._frame(),180)!={'status':'ready','protocol':'photo-resident-v29'}:
                raise ValueError('resident_readiness')
            self._ready=True
        except BaseException:
            await self._discard();raise

    def _startup_finished(self,task):
        try:task.result()
        except asyncio.CancelledError:return
        except BaseException:self._unhealthy=True

    async def start(self):
        if self._closing or self._unhealthy:raise PhotoServiceError(503,'PROCESSOR_UNAVAILABLE',True)
        if self.ready:return
        if self._start_task is None:
            self._start_task=asyncio.create_task(self._spawn())
            self._start_task.add_done_callback(self._startup_finished)
        await asyncio.shield(self._start_task)
        if not self.ready:raise PhotoServiceError(503,'PROCESSOR_UNAVAILABLE',True)

    async def close(self):
        self._closing=True
        if self._start_task is not None and not self._start_task.done():
            self._start_task.cancel();await asyncio.gather(self._start_task,return_exceptions=True)
        await self._discard()

    async def run(self,upload,request_id,engine,deadline):
        acquired=False;temporary=None;failed=False
        try:
            await asyncio.wait_for(self._slot.acquire(),max(0,deadline-time.monotonic()));acquired=True
            self._check_cancelled()
            await asyncio.wait_for(self.start(),max(0,deadline-time.monotonic()))
            self._check_cancelled()
            temporary=tempfile.TemporaryDirectory(prefix='blurfing-photo-v29-',dir=self.config.temp_root)
            root=Path(temporary.name);source=root/'input.png';source.write_bytes(upload.content);output=root/'output'
            job_id=uuid.uuid4().hex
            frame=dict(id=job_id,input=str(source),output=str(output),request_id=request_id)
            self._process.stdin.write((json.dumps(frame,separators=(',',':'))+'\n').encode('utf-8'))
            await asyncio.wait_for(self._process.stdin.drain(),max(0,deadline-time.monotonic()))
            self._check_cancelled()
            reply=await asyncio.wait_for(self._frame(),max(0,deadline-time.monotonic()))
            self._check_cancelled()
            if reply!={'status':'ok','id':job_id}:raise ValueError('resident_request_binding')
            path=output/'result.transport.json'
            if (output.is_symlink() or output.resolve().parent!=root.resolve() or path.is_symlink() or
                    not path.is_file() or path.resolve().parent!=output.resolve()):raise ValueError('resident_output_binding')
            with path.open('rb') as stream:content=stream.read(MAX_TRANSPORT_BYTES+1)
            if len(content)>MAX_TRANSPORT_BYTES:raise ValueError('resident_output_limit')
            payload=json.loads(content,object_pairs_hook=_unique_json_object,
                parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_output')))
            validated=validate_transport(payload,upload,request_id=request_id,engine=engine)
            if time.monotonic()>deadline:raise asyncio.TimeoutError()
            return validated
        except asyncio.TimeoutError as exc:
            failed=True;raise PhotoServiceError(504,'PROCESSOR_TIMEOUT',True) from exc
        except PhotoServiceError:
            failed=acquired;raise
        except asyncio.CancelledError:
            failed=acquired;raise
        except Exception as exc:
            failed=True;raise PhotoServiceError(500,'INVALID_PROCESSOR_RESULT',True) from exc
        finally:
            try:
                if failed and acquired:
                    # Stop all writers before removing private job files.
                    try:
                        if self._start_task is not None and not self._start_task.done():
                            self._start_task.cancel();await asyncio.gather(self._start_task,return_exceptions=True)
                        await self._discard()
                    except BaseException:
                        if temporary is not None:self._failed_temporaries.append(temporary);temporary=None
                        raise
                    if not self._closing and not self._unhealthy:
                        self._start_task=asyncio.create_task(self._spawn())
                        self._start_task.add_done_callback(self._startup_finished)
                if temporary is not None:temporary.cleanup()
            finally:
                if acquired:self._slot.release()


async def _disconnected(request):
    while not await request.is_disconnected():
        await asyncio.sleep(0.1)


def create_app(config=None):
    runtime = (PhotoResidentRuntime(config) if config.resident else PhotoSubprocessRuntime(config)) if config is not None else None
    @asynccontextmanager
    async def lifespan(_app):
        try:
            if isinstance(runtime,PhotoResidentRuntime):
                try:await runtime.start()
                except Exception:runtime._unhealthy=True
            yield
        finally:
            if isinstance(runtime,PhotoResidentRuntime):await runtime.close()
    application = FastAPI(title="BlurFing experimental photo V2", docs_url=None, redoc_url=None,lifespan=lifespan)
    application.add_middleware(BodyLimitMiddleware)
    application.state.photo_runtime = runtime

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        response = error_response(getattr(request.state, "request_id", ""), exc.status_code,
                                  {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INVALID_REQUEST"))
        body_headers = {"content-length", "content-type", "content-encoding", "transfer-encoding"}
        response.headers.update({name: value for name, value in (exc.headers or {}).items()
                                 if name.lower() not in body_headers})
        return response

    @application.exception_handler(Exception)
    async def internal_error(request, _exc):
        return error_response(getattr(request.state, "request_id", ""), 500, "INTERNAL_SERVER_ERROR", True)

    @application.get("/ready")
    async def ready():
        if runtime is None or runtime._unhealthy or (isinstance(runtime,PhotoResidentRuntime) and not runtime.ready):
            return error_response("", 503, "PROCESSOR_UNAVAILABLE", True)
        return {"status": "ready", "contract_version": "photo-experimental-v2",
                "result_kind": "experimental", "photo_engines": list(runtime.config.engines),
                "production_approved": False}

    @application.post("/v2/photo/protect")
    async def protect(request: Request):
        started = time.monotonic()
        request_id = ""
        claimed = False
        job = disconnect = None
        form = None
        try:
            if runtime is None or runtime._unhealthy:
                raise PhotoServiceError(503, "PROCESSOR_UNAVAILABLE", True)
            if request.headers.get("content-type", "").split(";", 1)[0].lower() != "multipart/form-data":
                raise PhotoServiceError(415, "MULTIPART_REQUIRED")
            try:
                form = await asyncio.wait_for(request.form(max_files=1, max_fields=4, max_part_size=1024),
                                              runtime.config.timeout_seconds)
            except PhotoServiceError:
                raise
            except asyncio.TimeoutError:
                raise PhotoServiceError(504, "PROCESSOR_TIMEOUT", True)
            except ClientDisconnect:
                raise PhotoServiceError(499, "CLIENT_DISCONNECTED")
            except Exception as exc:
                raise PhotoServiceError(400, "INVALID_MULTIPART") from exc
            fields = form.multi_items()
            if len(fields) != len(EXPECTED_FIELDS) or {key for key, _ in fields} != EXPECTED_FIELDS:
                raise PhotoServiceError(400, "INVALID_FORM_FIELDS")
            raw_id = form["request_id"]
            if not isinstance(raw_id, str) or REQUEST_ID_PATTERN.fullmatch(raw_id) is None:
                raise PhotoServiceError(400, "INVALID_REQUEST_ID")
            request_id = raw_id
            request.state.request_id = request_id
            if (not isinstance(form["method"], str) or form["method"] not in ENGINE_METHODS.values() or
                    form["scope"] != "automatic_photo" or not isinstance(form["strength"], str)):
                raise PhotoServiceError(400, "UNSUPPORTED_PHOTO_OPTIONS")
            try:
                strength = float(form["strength"])
            except ValueError:
                raise PhotoServiceError(400, "UNSUPPORTED_PHOTO_OPTIONS")
            if not math.isfinite(strength) or strength != 0.5:
                raise PhotoServiceError(400, "UNSUPPORTED_PHOTO_OPTIONS")
            engine = next(key for key, value in ENGINE_METHODS.items() if value == form["method"])
            if engine not in runtime.config.engines:
                raise PhotoServiceError(503, "PROCESSOR_UNAVAILABLE", True)
            image = form["image"]
            if not isinstance(image, UploadFile) or image.content_type != "image/png":
                raise PhotoServiceError(415, "RGB_PNG_REQUIRED")
            content = await image.read(MAX_IMAGE_BYTES + 1)
            if len(content) > MAX_IMAGE_BYTES:
                raise PhotoServiceError(413, "IMAGE_TOO_LARGE")
            try:
                upload = UploadedPhoto.decode(content)
            except TransportValidationError as exc:
                code = "IMAGE_TOO_LARGE" if str(exc) in ("PNG_byte_limit", "PNG_pixel_limit") else "RGB_EXIF1_PNG_REQUIRED"
                raise PhotoServiceError(413 if code == "IMAGE_TOO_LARGE" else 415, code) from exc
            runtime.claim(request_id)
            claimed = True
            deadline = started + runtime.config.timeout_seconds
            job = asyncio.create_task(runtime.run(upload, request_id, engine, deadline))
            disconnect = asyncio.create_task(_disconnected(request))
            done, _pending = await asyncio.wait((job, disconnect), return_when=asyncio.FIRST_COMPLETED)
            if disconnect in done:
                job.cancel()
                await asyncio.gather(job, return_exceptions=True)
                raise PhotoServiceError(499, "CLIENT_DISCONNECTED")
            result = await job
            result["processing_ms"] = int((time.monotonic() - started) * 1000)
            return JSONResponse(result)
        except PhotoServiceError as exc:
            return error_response(request_id, exc.status, exc.code, exc.retryable)
        finally:
            if disconnect is not None:
                disconnect.cancel()
                await asyncio.gather(disconnect, return_exceptions=True)
            if job is not None and not job.done():
                job.cancel()
                await asyncio.gather(job, return_exceptions=True)
            if claimed:
                runtime.release(request_id)
            if form is not None:
                await form.close()

    return application


app = create_app(PhotoRuntimeConfig.from_environment())
