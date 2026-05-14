"""
Anthropic-backed LLM client.
Handles structured output, parse resilience, and prompt-level retries.
"""

from __future__ import annotations
import json
from typing import Literal
import anthropic
from pydantic import ValidationError
from ..models import GeneratedArtifact, RepairContext, Spec
from .prompts import PromptBuilder

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8096


class LLMOutputParseError(RuntimeError):
    pass


class AnthropicLLMClient:
    """
    Satisfies the LLMClient protocol.
    temperature=0 for determinism; reasoning field ordered first to force CoT.
    """

    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        temperature: float = 0.0,
        max_retries: int = 2,
    ):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._prompts = PromptBuilder()

    def generate(self, spec: Spec) -> GeneratedArtifact:
        return self._call_with_retry(self._prompts.generate(spec), context="generate")

    def repair(self, artifact: GeneratedArtifact, context: RepairContext) -> GeneratedArtifact:
        return self._call_with_retry(self._prompts.repair(artifact, context), context="repair")

    # ── Private ───────────────────────────────────────────────────────────────

    def _call_with_retry(
        self, user_prompt: str, context: Literal["generate", "repair"]
    ) -> GeneratedArtifact:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                raw = self._call_api(user_prompt)
                return self._parse(raw)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                user_prompt = self._append_parse_correction(user_prompt, str(e))
        raise LLMOutputParseError(
            f"Failed to parse LLM output after {self._max_retries} attempts "
            f"during {context}: {last_error}"
        ) from last_error

    def _call_api(self, user_prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            temperature=self._temperature,
            system=self._prompts.system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def _parse(self, raw: str) -> GeneratedArtifact:
        cleaned = self._strip_fences(raw)
        data = json.loads(cleaned)
        return GeneratedArtifact.model_validate(data)

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return text.strip()

    @staticmethod
    def _append_parse_correction(prompt: str, error: str) -> str:
        return (
            f"{prompt}\n\n"
            f"## CORRECTION REQUIRED\n"
            f"Your previous response could not be parsed: {error}\n"
            f"Respond with valid JSON only. No markdown. No preamble."
        )
