"""Thin DecisionBackend-shaped adapter over local Ollama token logprobs (lab, offline scoring only).

Gives the Qwen baseline row of kvnloo/hermes-agent#319 a real true/false distribution: the first
generated token's top logprobs are summed per label and renormalised over {false, true}.  When no
label token carries mass the request fails (a counted coverage gap); it never falls back to a
one-hot answer, which would make log-loss meaningless.  Boolean questions only; loopback only.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from typing import Any, Callable

from z0int.backends.base import BackendCapabilities, BackendHealth, DecisionAnswer, DecisionResult

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
TOP_LOGPROBS = 20


def _http_post(base_url: str) -> Callable[[str, dict], dict]:
    def post(path: str, body: dict) -> dict:
        req = urllib.request.Request(base_url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read())
    return post


class OllamaLogprobBackend:
    def __init__(self, model: str, *, base_url: str | None = None,
                 post: Callable[[str, dict], dict] | None = None, revision: str | None = None,
                 keep_alive: str = "10m") -> None:
        self.model = model
        self.base_url = (base_url or os.environ.get("Z0INT_OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._post = post or _http_post(self.base_url)
        self.keep_alive = keep_alive
        self.revision = revision if revision is not None else self._digest()

    def _digest(self) -> str:
        """Exact model identity; raises when the server is down or lacks the model (an outage)."""
        with urllib.request.urlopen(self.base_url + "/api/tags", timeout=30) as response:
            listing = json.loads(response.read())
        for entry in listing.get("models", []):
            if entry.get("name") == self.model:
                return str(entry.get("digest"))
        raise LookupError(f"model {self.model!r} is not served at {self.base_url}")

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(id=f"ollama:{self.model}", local=True, supports_boolean=True,
                                   supports_choice=False, supports_score=False, max_choice_options=0,
                                   max_score_levels=0, kind="decision", returns_distribution=True,
                                   autoregressive_decode=True,
                                   description="Ollama first-token logprob readout (lab baseline)")

    def health(self, *, load: bool = False) -> BackendHealth:
        return BackendHealth(id=f"ollama:{self.model}", configured=True, ready=True, model=self.model)

    @staticmethod
    def _prompt(question, state: Any) -> str:
        false_c = question.false_criterion or "no"
        true_c = question.true_criterion or "yes"
        return (f"{question.instructions}\nfalse = {false_c}\ntrue = {true_c}\n"
                f"State: {json.dumps(state, sort_keys=True)}\nAnswer with exactly one word: true or false.")

    def evaluate(self, request) -> DecisionResult:
        started = time.perf_counter()
        answers = []
        covered = []
        for question in request.questions:
            if question.type != "boolean":
                raise ValueError(f"ollama logprob adapter supports boolean questions only, not {question.type}")
            out = self._post("/api/chat", {
                "model": self.model, "stream": False, "keep_alive": self.keep_alive,
                "messages": [{"role": "user", "content": self._prompt(question, request.state)}],
                "options": {"temperature": 0, "num_predict": 1, "seed": 0},
                "logprobs": True, "top_logprobs": TOP_LOGPROBS,
            })
            steps = out.get("logprobs") or []
            if not steps:
                raise ValueError("ollama returned no logprobs")
            mass = {"false": 0.0, "true": 0.0}
            for item in steps[0].get("top_logprobs") or []:
                token = str(item.get("token", "")).strip().lower()
                if token in mass:
                    mass[token] += math.exp(float(item["logprob"]))
            total = mass["false"] + mass["true"]
            if total <= 0.0:
                raise ValueError("no probability mass on a true/false first token")
            if mass["false"] <= 0.0 or mass["true"] <= 0.0:
                # Only one label is in the top-k: renormalising would emit exactly 0/1 (one-hot). Refuse.
                missing = "false" if mass["false"] <= 0.0 else "true"
                raise ValueError(f"label {missing!r} absent from the top-{TOP_LOGPROBS} first-token logprobs")
            probs = {"false": mass["false"] / total, "true": mass["true"] / total}
            covered.append(total)
            answers.append(DecisionAnswer(question_id=question.id, type="boolean", probabilities=probs,
                                          value=probs["true"] >= 0.5, confidence=max(probs.values())))
        return DecisionResult(backend=f"ollama:{self.model}", model=self.model, revision=self.revision,
                              answers=tuple(answers), latency_ms=(time.perf_counter() - started) * 1000.0,
                              diagnostics={"covered_mass": min(covered), "readout": "first_token_top_logprobs",
                                           "top_logprobs": TOP_LOGPROBS, "base_url": self.base_url})
