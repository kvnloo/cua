import os
from typing import Any, AsyncIterator, Iterator

from cua_core.http import cua_version_headers
from litellm import acompletion, completion
from litellm.llms.custom_llm import CustomLLM
from litellm.types.utils import GenericStreamingChunk, ModelResponse


class CUAAdapter(CustomLLM):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, **_: Any):
        super().__init__()
        self.base_url = base_url or os.environ.get("CUA_BASE_URL") or "https://inference.cua.ai/v1"
        self.api_key = (
            api_key or os.environ.get("CUA_INFERENCE_API_KEY") or os.environ.get("CUA_API_KEY")
        )

    def _normalize_model(self, model: str) -> str:
        """Strip known prefixes to get the base model name."""
        known_prefixes = ("cua/", "anthropic/", "gemini/", "google/", "openai/")
        if not isinstance(model, str):
            # An explicit model=None (or other non-string) reaches the adapter
            # when litellm forwards kwargs verbatim; calling .startswith on it
            # raised AttributeError out of the custom-LLM path (non-retryable
            # -> run-kill). Normalize to "" so downstream validation, not a
            # crash, surfaces the problem.
            return ""
        result = model
        for prefix in known_prefixes:
            if result.startswith(prefix):
                result = result[len(prefix) :]
        return result

    def _resolve_route(self, model: str, api_base: str) -> tuple[str, str]:
        """Return (prefixed_model, api_base) for the CUA inference API."""
        if not isinstance(model, str):
            # "x" in None raised TypeError on this non-retryable path; see
            # _normalize_model for why we degrade to "" instead of crashing.
            model = ""
        if not isinstance(api_base, str):
            api_base = self.base_url or ""
        if "anthropic/" in model:
            return f"anthropic/{self._normalize_model(model)}", api_base.removesuffix("/v1")
        elif "gemini/" in model or "google/" in model:
            return f"gemini/{self._normalize_model(model)}", api_base + "/gemini"
        else:
            return f"openai/{self._normalize_model(model)}", api_base

    def _resolve_api_key(self, kwargs: dict | None = None) -> str:
        """Resolve the CUA API key, raising a clear error if missing.

        Checks kwargs (from ComputerAgent api_key param) then falls back
        to self.api_key (from CUA_API_KEY / CUA_INFERENCE_API_KEY env vars).

        This validation must run before the inner litellm call because that
        call uses an anthropic/ or openai/ model prefix, which would cause
        litellm to fall back to ANTHROPIC_API_KEY from env — sending the
        wrong key to the CUA inference endpoint.
        """
        resolved = (kwargs.get("api_key") if kwargs else None) or self.api_key
        if not resolved:
            raise ValueError(
                "No CUA API key provided for cua/ model inference. "
                "Please either set the CUA_API_KEY environment variable "
                "or pass api_key to ComputerAgent()."
            )
        return resolved

    def completion(self, *args, **kwargs) -> ModelResponse:
        model, api_base = self._resolve_route(
            kwargs.get("model", ""), kwargs.get("api_base") or self.base_url
        )

        api_key = self._resolve_api_key(kwargs)

        # Ensure the CUA inference API always receives Bearer auth;
        # merge caller headers first, then force Authorization so it cannot be overridden.
        extra_headers = {}
        if "extra_headers" in kwargs:
            provided = kwargs.pop("extra_headers")
            # A non-dict extra_headers (malformed caller kwargs) made
            # dict.update raise TypeError on the non-retryable custom-LLM
            # path; ignore it instead of killing the run.
            if isinstance(provided, dict):
                extra_headers.update(provided)
        extra_headers["Authorization"] = f"Bearer {api_key}"

        params = {
            "model": model,
            "messages": kwargs.get("messages", []),
            "api_base": api_base,
            "api_key": api_key,
            "extra_headers": extra_headers,
            "stream": False,
        }

        # Forward tools if provided
        if "tools" in kwargs:
            params["tools"] = kwargs["tools"]

        if "optional_params" in kwargs:
            protected_keys = {"api_key", "extra_headers", "model", "api_base", "stream"}
            optional = kwargs["optional_params"]
            # .items() on a non-dict raised AttributeError on the
            # non-retryable path; ignore malformed values instead.
            filtered = (
                {k: v for k, v in optional.items() if k not in protected_keys}
                if isinstance(optional, dict)
                else {}
            )
            params.update(filtered)
            del kwargs["optional_params"]

        if "headers" in kwargs:
            if isinstance(kwargs["headers"], dict):
                params["headers"] = kwargs["headers"]
            del kwargs["headers"]

        # Always include CUA version headers
        version_hdrs = cua_version_headers()
        if version_hdrs:
            existing = params.get("headers")
            # ** on a non-dict raised TypeError; drop malformed headers.
            params["headers"] = {
                **version_hdrs,
                **(existing if isinstance(existing, dict) else {}),
            }

        # Print dropped parameters
        original_keys = set(kwargs.keys())
        used_keys = set(params.keys())  # Only these are extracted from kwargs
        ignored_keys = {
            "litellm_params",
            "client",
            "print_verbose",
            "acompletion",
            "timeout",
            "logging_obj",
            "encoding",
            "custom_prompt_dict",
            "model_response",
            "logger_fn",
        }
        dropped_keys = original_keys - used_keys - ignored_keys
        if dropped_keys:
            dropped_keyvals = {k: kwargs[k] for k in dropped_keys}
            # print(f"CUAAdapter.completion: Dropped parameters: {dropped_keyvals}")

        return completion(**params)  # type: ignore

    async def acompletion(self, *args, **kwargs) -> ModelResponse:
        model, api_base = self._resolve_route(
            kwargs.get("model", ""), kwargs.get("api_base") or self.base_url
        )

        api_key = self._resolve_api_key(kwargs)

        # Ensure the CUA inference API always receives Bearer auth;
        # merge caller headers first, then force Authorization so it cannot be overridden.
        extra_headers = {}
        if "extra_headers" in kwargs:
            provided = kwargs.pop("extra_headers")
            # A non-dict extra_headers (malformed caller kwargs) made
            # dict.update raise TypeError on the non-retryable custom-LLM
            # path; ignore it instead of killing the run.
            if isinstance(provided, dict):
                extra_headers.update(provided)
        extra_headers["Authorization"] = f"Bearer {api_key}"

        params = {
            "model": model,
            "messages": kwargs.get("messages", []),
            "api_base": api_base,
            "api_key": api_key,
            "extra_headers": extra_headers,
            "stream": False,
        }

        # Forward tools if provided
        if "tools" in kwargs:
            params["tools"] = kwargs["tools"]

        if "optional_params" in kwargs:
            protected_keys = {"api_key", "extra_headers", "model", "api_base", "stream"}
            optional = kwargs["optional_params"]
            # .items() on a non-dict raised AttributeError on the
            # non-retryable path; ignore malformed values instead.
            filtered = (
                {k: v for k, v in optional.items() if k not in protected_keys}
                if isinstance(optional, dict)
                else {}
            )
            params.update(filtered)
            del kwargs["optional_params"]

        if "headers" in kwargs:
            if isinstance(kwargs["headers"], dict):
                params["headers"] = kwargs["headers"]
            del kwargs["headers"]

        # Always include CUA version headers
        version_hdrs = cua_version_headers()
        if version_hdrs:
            existing = params.get("headers")
            # ** on a non-dict raised TypeError; drop malformed headers.
            params["headers"] = {
                **version_hdrs,
                **(existing if isinstance(existing, dict) else {}),
            }

        # Print dropped parameters
        original_keys = set(kwargs.keys())
        used_keys = set(params.keys())  # Only these are extracted from kwargs
        ignored_keys = {
            "litellm_params",
            "client",
            "print_verbose",
            "acompletion",
            "timeout",
            "logging_obj",
            "encoding",
            "custom_prompt_dict",
            "model_response",
            "logger_fn",
        }
        dropped_keys = original_keys - used_keys - ignored_keys
        if dropped_keys:
            dropped_keyvals = {k: kwargs[k] for k in dropped_keys}
            # print(f"CUAAdapter.acompletion: Dropped parameters: {dropped_keyvals}")

        response = await acompletion(**params)  # type: ignore

        return response

    def streaming(self, *args, **kwargs) -> Iterator[GenericStreamingChunk]:
        params = dict(kwargs)
        model, api_base = self._resolve_route(
            params.get("model", ""), params.get("api_base") or self.base_url
        )
        api_key = self._resolve_api_key(kwargs)

        # Ensure the CUA inference API always receives Bearer auth;
        # merge caller headers first, then force Authorization so it cannot be overridden.
        extra_headers = {}
        if "extra_headers" in params:
            provided = params.pop("extra_headers")
            if isinstance(provided, dict):
                extra_headers.update(provided)
        extra_headers["Authorization"] = f"Bearer {api_key}"

        params.update(
            {
                "model": model,
                "api_base": api_base,
                "api_key": api_key,
                "extra_headers": extra_headers,
                "stream": True,
            }
        )
        # Always include CUA version headers
        version_hdrs = cua_version_headers()
        if version_hdrs:
            existing = params.get("headers")
            # ** on a non-dict raised TypeError; drop malformed headers.
            params["headers"] = {
                **version_hdrs,
                **(existing if isinstance(existing, dict) else {}),
            }
        # Yield chunks directly from LiteLLM's streaming generator
        for chunk in completion(**params):  # type: ignore
            yield chunk  # type: ignore

    async def astreaming(self, *args, **kwargs) -> AsyncIterator[GenericStreamingChunk]:
        params = dict(kwargs)
        model, api_base = self._resolve_route(
            params.get("model", ""), params.get("api_base") or self.base_url
        )
        api_key = self._resolve_api_key(kwargs)

        # Ensure the CUA inference API always receives Bearer auth;
        # merge caller headers first, then force Authorization so it cannot be overridden.
        extra_headers = {}
        if "extra_headers" in params:
            provided = params.pop("extra_headers")
            if isinstance(provided, dict):
                extra_headers.update(provided)
        extra_headers["Authorization"] = f"Bearer {api_key}"

        params.update(
            {
                "model": model,
                "api_base": api_base,
                "api_key": api_key,
                "extra_headers": extra_headers,
                "stream": True,
            }
        )
        # Always include CUA version headers
        version_hdrs = cua_version_headers()
        if version_hdrs:
            existing = params.get("headers")
            # ** on a non-dict raised TypeError; drop malformed headers.
            params["headers"] = {
                **version_hdrs,
                **(existing if isinstance(existing, dict) else {}),
            }
        stream = await acompletion(**params)  # type: ignore
        async for chunk in stream:  # type: ignore
            yield chunk  # type: ignore
