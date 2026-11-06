"""Clearly labeled mock or an actual, separately configured Ollama VLM."""
import base64
import os

import httpx
from fastapi import HTTPException

MAX_INFERENCE_FRAMES = 6


def select_evenly(frames: list, maximum: int = MAX_INFERENCE_FRAMES) -> list:
    if len(frames) <= maximum:
        return frames
    indices = [round(i * (len(frames) - 1) / (maximum - 1)) for i in range(maximum)]
    return [frames[i] for i in indices]


async def answer_question(question: str, jpegs: list[bytes], timestamps: list[str]) -> tuple[str, str]:
    mode = os.environ.get("INFERENCE_MODE", "mock").lower()
    if mode == "mock":
        return (
            "MOCK RESPONSE — No image understanding has run. "
            f"The API received {len(jpegs)} JPEG frame(s) for the question: “{question}”. "
            "Set INFERENCE_MODE=ollama and connect a working vision-language model for real answers.",
            "mock",
        )
    if mode != "ollama":
        raise HTTPException(503, "Unknown inference mode; choose mock or ollama")
    if not jpegs:
        raise HTTPException(400, "No visual evidence supplied")

    url = os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:3b")
    prompt = (
        "You are analyzing sampled frames from a camera in chronological order. "
        "Only describe things supported by visible frames. Do not invent intervening events. "
        "Explicitly say when frame sampling makes something uncertain. "
        "Source frame timestamps (UTC, in order): " + ", ".join(timestamps) + "\n"
        "User question: " + question
    )
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "user", "content": prompt,
             "images": [base64.b64encode(jpeg).decode("ascii") for jpeg in jpegs]}
        ],
        "options": {"temperature": 0.2},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=7.0)) as client:
            response = await client.post(url + "/api/chat", json=payload)
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content", "").strip()
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Vision-language service timed out") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Vision-language service is unavailable or returned an invalid response") from exc
    if not answer:
        raise HTTPException(502, "Vision-language service returned an empty answer")
    return answer, "ollama"
