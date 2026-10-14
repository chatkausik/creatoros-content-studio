"""The only inference boundary: all models are accessed through Mesh API.

There are no hidden network retries. Schema errors receive at most one bounded
correction. Successful responses are cached before a pipeline node is committed,
so restarting a node does not pay again for a completed model response.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import json
import logging
import os
import socket
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError


MESH_BASE_URL = "https://api.meshapi.ai/v1"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class MeshError(RuntimeError):
    """A user-safe error that never includes authorization or response bodies."""

    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics


class ImageDownloadError(MeshError):
    """Transient fetch failure: keep the paid response for a download-only retry."""

    def __init__(self, message: str):
        super().__init__(message, {"image_retry_action": "retry_download"})


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _wire_schema(schema: type[BaseModel]) -> dict:
    """Keep the portable strict JSON-schema subset; validate constraints locally."""
    value = copy.deepcopy(schema.model_json_schema())

    def clean(item):
        if isinstance(item, dict):
            for name in ("default", "minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"):
                item.pop(name, None)
            if item.get("type") == "object":
                item["additionalProperties"] = False
                item["required"] = list(item.get("properties", {}))
            for child in item.values():
                clean(child)
        elif isinstance(item, list):
            for child in item:
                clean(child)

    clean(value)
    return value


class MeshClient:
    def __init__(self, settings):
        self.settings = settings
        configured = getattr(settings, "mesh_base_url", MESH_BASE_URL).rstrip("/")
        if configured != MESH_BASE_URL:
            raise MeshError("All inference must use https://api.meshapi.ai/v1.")
        self.base_url = MESH_BASE_URL
        self.model = getattr(settings, "chat_model", "openai/gpt-4o-mini")
        self.image_model = getattr(settings, "image_model", "openai/gpt-image-1-mini")
        self.api_key = getattr(settings, "mesh_api_key", "")
        self.data_dir = Path(settings.data_dir)
        self.cache_dir = self.data_dir / "mesh_cache"
        self.timeout = float(getattr(settings, "mesh_timeout", 90.0))
        self.usage: list[dict] = []

    async def _post(self, endpoint: str, payload: dict, timeout: float | None = None, cache: bool = True) -> dict:
        if not self.api_key:
            raise MeshError("Add MESH_API_KEY to .env to run live Mesh generation.")
        if endpoint not in {"chat/completions", "images/generations"}:
            raise MeshError("Unsupported Mesh inference endpoint.")
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            if not cache:
                headers["X-Mesh-Cache"] = "no-store"
            async with httpx.AsyncClient(timeout=timeout or self.timeout, trust_env=False, follow_redirects=False) as client:
                response = await client.post(
                    f"{self.base_url}/{endpoint}",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException:
            raise MeshError("Mesh timed out. Your completed steps are saved; retry the failed step.") from None
        except httpx.HTTPError:
            raise MeshError("Could not connect to Mesh. Check your connection and retry.") from None
        if not 200 <= response.status_code < 300:
            messages = {
                400: "Mesh rejected the request. Check that the selected model supports structured output.",
                401: "Mesh rejected the API key. Update MESH_API_KEY and retry.",
                403: "This Mesh key cannot access the selected model.",
                402: "Mesh credit or spend limit was reached. Add credit or adjust the limit, then retry.",
                404: "The selected model or Mesh endpoint is unavailable.",
                422: "Mesh rejected the request format for this model.",
                429: "Mesh is rate limiting requests. Wait briefly and retry the failed step.",
            }
            raise MeshError(messages.get(response.status_code, f"Mesh returned HTTP {response.status_code}. Retry the saved run."))
        try:
            result = response.json()
        except ValueError:
            raise MeshError("Mesh returned an unreadable response. Retry the failed step.") from None
        if not isinstance(result, dict):
            raise MeshError("Mesh returned an unexpected response shape.")
        return result

    def _record_usage(self, response: dict, model: str, cache_hit: bool, elapsed: float = 0) -> dict:
        raw = response.get("usage") or {}
        actual_model = response.get("model")
        record = {"model": model, "requested_model": model,
                  "actual_model": actual_model[:200] if isinstance(actual_model, str) else None,
                  "cache_hit": cache_hit, "elapsed_seconds": round(elapsed, 3)}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost", "cost_usd", "total_cost"):
            value = raw.get(key) if isinstance(raw, dict) else None
            if isinstance(value, (int, float)):
                record[key] = value
        self.usage.append(record)
        logger.info("mesh_usage %s", json.dumps(record))
        return record

    async def complete_json(self, system: str, user: str, schema: type[T], temperature: float = 0.2, cache: bool = True) -> T:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": 2200,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True, "schema": _wire_schema(schema)},
            },
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        cache_path = self.cache_dir / f"chat-{digest}.json"
        cached = _read_json(cache_path) if cache else None
        if cached:
            try:
                parsed = schema.model_validate(cached["output"])
                self._record_usage(cached, self.model, True)
                return parsed
            except (ValidationError, KeyError):
                pass
        for attempt in range(2):
            started = time.monotonic()
            # A correction must be evaluated afresh, even if gateway cache is
            # enabled for the original request.
            response = await self._post("chat/completions", payload, cache=cache and attempt == 0)
            self._record_usage(response, self.model, False, time.monotonic() - started)
            content = None
            try:
                message = response["choices"][0]["message"]
                if message.get("refusal"):
                    raise MeshError("The model could not fulfill this request. Review the brief before retrying.")
                content = message.get("content")
                if not isinstance(content, str):
                    raise ValueError("Expected JSON text")
                parsed = schema.model_validate_json(content)
            except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
                errors = [{"type": "invalid_response", "loc": [], "msg": "Response must contain JSON text matching the requested schema"}]
                if isinstance(error, ValidationError):
                    errors = error.errors(include_input=False, include_context=False, include_url=False)[:8]
                diagnostics = {"schema": schema.__name__, "attempt": attempt + 1, "errors": errors, "diagnostic_id": digest}
                # Raw rejected output remains in private application data for
                # debugging; public run diagnostics include only schema errors.
                _write_json(self.data_dir / "mesh_diagnostics" / f"{digest}-{attempt + 1}.json",
                            {**diagnostics, "output": content, "model": response.get("model")})
                if attempt:
                    raise MeshError(f"Mesh returned invalid structured output twice ({schema.__name__}). The failed step can be retried.", diagnostics) from None
                issues = "Return a complete JSON object matching the schema."
                if isinstance(error, ValidationError):
                    issues += " Fix: " + "; ".join(
                        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                        for item in errors[:6]
                    )
                if isinstance(content, str):
                    payload["messages"].append({"role": "assistant", "content": content[:32000]})
                payload["messages"].append({"role": "user", "content": issues})
                continue
            if cache:
                _write_json(cache_path, {"output": parsed.model_dump(), "usage": response.get("usage", {}), "model": response.get("model")})
            return parsed
        raise MeshError("Structured generation did not complete.")

    async def generate_image(self, prompt: str, request_id: str | None = None) -> dict:
        """Retry the same request without paying twice; a new id explicitly regenerates."""
        payload = {"model": self.image_model, "prompt": prompt, "n": 1, "quality": "low", "size": "1024x1024", "response_format": "b64_json"}
        cache_input = {**payload, **({"request_id": request_id} if request_id else {})}
        digest = hashlib.sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()
        cache_path = self.cache_dir / f"image-{digest}.json"
        cached = _read_json(cache_path)
        if cached and (self.data_dir / "assets" / Path(cached.get("image_url", "")).name).is_file():
            result = copy.deepcopy(cached)
            usage = self._record_usage({"model": cached.get("actual_model")}, self.image_model, True)
            usage.update({"stage": "image_generation", "request_id": request_id or digest})
            result["usage"] = [usage]
            result["cache_hit"] = True
            return result
        # Save the completed response before normalization/download. A download
        # failure can be retried without a second paid generation request.
        raw_cache = self.cache_dir / f"image-response-{digest}.json"
        invalid_marker = self.cache_dir / f"image-invalid-{digest}.json"
        response = _read_json(raw_cache)
        raw_cache_hit = response is not None
        elapsed = 0.0
        if response is None:
            started = time.monotonic()
            response = await self._post("images/generations", payload, timeout=max(240.0, self.timeout), cache=not bool(request_id) and not invalid_marker.exists())
            elapsed = time.monotonic() - started
            _write_json(raw_cache, response)
        usage = self._record_usage(response if not raw_cache_hit else {"model": response.get("model")}, self.image_model, raw_cache_hit, elapsed)
        usage.update({"stage": "image_generation", "request_id": request_id or digest, "download_retry": raw_cache_hit})
        try:
            entry = response["data"][0]
            if not isinstance(entry, dict):
                raise MeshError("Mesh returned an invalid image entry.")
            image_bytes = await normalize_image(entry)
        except ImageDownloadError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, MeshError) as error:
            # Only usable or transiently unavailable image responses survive.
            # Keeping invalid JSON/base64 here poisoned every later retry.
            raw_cache.unlink(missing_ok=True)
            _write_json(invalid_marker, {"invalidated_at": datetime.now(timezone.utc).isoformat()})
            message = str(error) if isinstance(error, MeshError) else "Mesh returned no image."
            raise MeshError(message + " The unusable response was discarded; regenerate the visual.", {"image_retry_action": "regenerate"}) from None
        asset_path = save_image(self.data_dir, image_bytes)
        result = {
            "image_url": f"/assets/{asset_path.name}", "image_prompt": prompt,
            "model": self.image_model, "requested_model": self.image_model,
            "actual_model": usage["actual_model"], "source": "mesh",
            "request_id": request_id or digest, "created_at": datetime.now(timezone.utc).isoformat(),
            "content_sha256": hashlib.sha256(image_bytes).hexdigest(), "cache_hit": raw_cache_hit,
            "usage": [copy.deepcopy(usage)],
        }
        _write_json(cache_path, result)
        invalid_marker.unlink(missing_ok=True)
        return result


async def normalize_image(entry: dict) -> bytes:
    """Accept Mesh's base64, data-URI and public HTTPS raster-image variants."""
    raw_base64 = entry.get("b64_json")
    url = entry.get("url")
    if isinstance(url, str) and url.startswith("data:"):
        header, separator, raw_base64 = url.partition(",")
        if not separator or header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
            raise MeshError("Mesh returned an unsupported image data URI.")
    if isinstance(raw_base64, str):
        if len(raw_base64) > (MAX_IMAGE_BYTES * 4 // 3) + 8:
            raise MeshError("Generated image exceeds the 20 MB limit.")
        try:
            result = base64.b64decode(raw_base64, validate=True)
        except (ValueError, base64.binascii.Error):
            raise MeshError("Mesh returned invalid image bytes.") from None
    elif isinstance(url, str):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise MeshError("Image download requires a public HTTPS URL.")
        try:
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        except OSError:
            raise ImageDownloadError("Could not resolve the generated image host. Retry the saved visual download.") from None
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise MeshError("Image download host must use a public IP address.")
        chunks = []
        size = 0
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        if response.status_code in {400, 401, 403, 404, 410}:
                            raise MeshError("The generated image URL is no longer available.")
                        raise ImageDownloadError("Image download failed. Retry the saved visual response.")
                    content_length = response.headers.get("content-length", "")
                    if content_length.isdigit() and int(content_length) > MAX_IMAGE_BYTES:
                        raise MeshError("Generated image exceeds the 20 MB limit.")
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_IMAGE_BYTES:
                            raise MeshError("Generated image exceeds the 20 MB limit.")
                        chunks.append(chunk)
        except httpx.HTTPError:
            raise ImageDownloadError("Image download failed. Retry the saved visual response.") from None
        result = b"".join(chunks)
    else:
        raise MeshError("Mesh returned neither image bytes nor a download URL.")
    if not result or len(result) > MAX_IMAGE_BYTES:
        raise MeshError("Generated image is empty or exceeds the 20 MB limit.")
    image_extension(result)
    return result


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    raise MeshError("The generated asset is not a supported PNG, JPEG, or WebP image.")


def save_image(data_dir: Path, data: bytes) -> Path:
    extension = image_extension(data)
    target = Path(data_dir) / "assets" / f"{hashlib.sha256(data).hexdigest()[:24]}.{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
    return target
