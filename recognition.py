"""ACRCloud music identification client."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import re
import time
from pathlib import Path

import aiohttp

IDENTIFY_PATH = "/v1/identify"
MAX_SAMPLE_BYTES = 5 * 1024 * 1024


class RecognitionError(RuntimeError):
    """A safe, user-facing recognition failure."""


class RecognitionNotConfigured(RecognitionError):
    """Raised when ACRCloud credentials have not been configured."""


def make_signature(
    access_key: str,
    access_secret: str,
    timestamp: str,
    *,
    data_type: str = "audio",
) -> str:
    """Create an ACRCloud Identify Protocol V1 HMAC signature."""
    value = "\n".join(
        ("POST", IDENTIFY_PATH, access_key, data_type, "1", timestamp)
    ).encode("utf-8")
    digest = hmac.new(access_secret.encode("utf-8"), value, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


class ACRCloudRecognizer:
    def __init__(self) -> None:
        self.host = os.getenv("ACR_HOST", "").strip()
        self.access_key = os.getenv("ACR_ACCESS_KEY", "").strip()
        self.access_secret = os.getenv("ACR_ACCESS_SECRET", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.host and self.access_key and self.access_secret)

    async def identify(self, sample_path: Path) -> dict | None:
        if not self.configured:
            raise RecognitionNotConfigured("ACRCloud is not configured")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.host):
            raise RecognitionError("Invalid ACRCloud host")

        try:
            sample_size = sample_path.stat().st_size
        except OSError as exc:
            raise RecognitionError("Audio sample is unavailable") from exc

        if sample_size <= 0 or sample_size >= MAX_SAMPLE_BYTES:
            raise RecognitionError("Audio sample must be smaller than 5 MB")

        sample = await asyncio.to_thread(sample_path.read_bytes)
        timestamp = str(int(time.time()))
        signature = make_signature(self.access_key, self.access_secret, timestamp)
        form = aiohttp.FormData()
        form.add_field("access_key", self.access_key)
        form.add_field("sample_bytes", str(len(sample)))
        form.add_field("timestamp", timestamp)
        form.add_field("signature", signature)
        form.add_field("data_type", "audio")
        form.add_field("signature_version", "1")
        form.add_field(
            "sample",
            sample,
            filename=sample_path.name,
            content_type="application/octet-stream",
        )

        timeout = aiohttp.ClientTimeout(total=25)
        url = f"https://{self.host}{IDENTIFY_PATH}"
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=form) as response:
                    if response.status >= 400:
                        raise RecognitionError("ACRCloud request failed")
                    payload = await response.json(content_type=None)
        except RecognitionError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise RecognitionError("ACRCloud could not be reached") from exc

        status = payload.get("status") or {}
        if status.get("code") != 0:
            return None

        matches = (payload.get("metadata") or {}).get("music") or []
        return matches[0] if matches else None
