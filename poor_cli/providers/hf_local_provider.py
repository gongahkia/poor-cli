"""Local HuggingFace Transformers provider with latent-state access."""

from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    HF_LOCAL_AVAILABLE = True
except ImportError:
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None
    HF_LOCAL_AVAILABLE = False

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, UsageMetadata
from .capability import PROVIDER_CAPABILITIES
from ..exceptions import ConfigurationError, setup_logger
from ..provider_catalog import default_model_for_provider

logger = setup_logger(__name__)


class HFLocalProvider(BaseProvider):
    """Local HF Transformers provider.

    This provider is intentionally toolless: it exists for local text generation
    and latent hidden-state hand-off where the model internals are available.
    """

    capabilities = PROVIDER_CAPABILITIES["hf_local"]
    available = HF_LOCAL_AVAILABLE

    def __init__(
        self,
        api_key: str = "",
        model_name: str = default_model_for_provider("hf_local"),
        max_retries: int = 0,
        retry_delay: float = 0.0,
        timeout: float = 300.0,
        device: Optional[str] = None,
        dtype: Optional[str] = None,
        **kwargs: Any,
    ):
        if not HF_LOCAL_AVAILABLE:
            raise ConfigurationError(
                "HF local provider requires torch and transformers. "
                "Install with: pip install 'poor-cli[hf-local]'"
            )
        super().__init__(api_key, model_name, **kwargs)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.device = device or os.environ.get("POOR_CLI_HF_DEVICE") or self._default_device()
        self.dtype_name = dtype or os.environ.get("POOR_CLI_HF_DTYPE") or self._default_dtype(self.device)
        self.messages: List[Dict[str, str]] = []
        self.system_instruction: Optional[str] = None
        self.tools: Optional[List[Dict[str, Any]]] = None
        self.model = None
        self.tokenizer = None
        self._latent_orchestrator = None

    @staticmethod
    def _default_device() -> str:
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _default_dtype(device: str) -> str:
        return "float32" if device == "cpu" else "bfloat16"

    async def initialize(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ):
        self.tools = tools or None
        if self.tools:
            logger.warning("HF local provider ignores tool declarations")
        self.system_instruction = system_instruction
        await asyncio.wait_for(asyncio.to_thread(self._load_model), timeout=self.timeout)

    def _load_model(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return
        dtype = getattr(torch, self.dtype_name)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(self.device)
        self.model.eval()
        logger.info("HF local model initialized: %s on %s", self.model_name, self.device)

    def _build_messages(self, message: Any) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if self.system_instruction:
            messages.append({"role": "system", "content": self.system_instruction})
        if self.prompt_prefix:
            messages.append({"role": "user", "content": self.prompt_prefix})
        messages.extend(self.messages)
        if isinstance(message, str):
            messages.append({"role": "user", "content": message})
        elif isinstance(message, list):
            messages.extend(message)
        elif isinstance(message, dict):
            messages.append(message)
        else:
            messages.append({"role": "user", "content": str(message)})
        return messages

    def _render_prompt(self, messages: List[Dict[str, str]]) -> str:
        if hasattr(self.tokenizer, "apply_chat_template") and getattr(self.tokenizer, "chat_template", None):
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        rendered = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            rendered.append(f"{role}: {content}")
        rendered.append("assistant:")
        return "\n".join(rendered)

    async def send_message(self, message: Any, **kwargs: Any) -> ProviderResponse:
        if self.model is None or self.tokenizer is None:
            await self.initialize(system_instruction=self.system_instruction)
        return await asyncio.wait_for(
            asyncio.to_thread(self._send_message_sync, message),
            timeout=self.timeout,
        )

    def _send_message_sync(self, message: Any) -> ProviderResponse:
        messages = self._build_messages(message)
        prompt = self._render_prompt(messages)
        encoded = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        max_new_tokens = self.economy_max_output_tokens or int(self.config.get("max_new_tokens", 512))
        with torch.no_grad():
            output = self.model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = output[0][encoded.input_ids.shape[1]:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        self._append_user_message(message)
        self.messages.append({"role": "assistant", "content": text})
        usage = UsageMetadata(
            input_tokens=int(encoded.input_ids.shape[1]),
            output_tokens=int(new_tokens.shape[0]),
            total_tokens=int(encoded.input_ids.shape[1] + new_tokens.shape[0]),
        )
        return ProviderResponse(
            content=text,
            role="assistant",
            finish_reason="stop",
            metadata={"model": self.model_name, "device": self.device},
            usage=usage,
        )

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        response = await self.send_message(message)
        yield response

    def _append_user_message(self, message: Any) -> None:
        if isinstance(message, str):
            self.messages.append({"role": "user", "content": message})
        elif isinstance(message, list):
            self.messages.extend(message)
        elif isinstance(message, dict):
            self.messages.append(message)
        else:
            self.messages.append({"role": "user", "content": str(message)})

    async def clear_history(self):
        self.messages = []

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        self.messages = [
            {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
            for message in messages
            if message.get("role") != "system"
        ]

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=False,
            supports_function_calling=False,
            supports_system_instructions=True,
            max_context_tokens=32768,
            supports_json_mode=False,
            supports_structured_output=False,
            supports_latent_communication=True,
        )

    def get_provider_name(self) -> str:
        return "hf_local"

    async def run_latent_pipeline(
        self,
        task: str,
        max_new_tokens: int = 512,
        latent_steps: int = 20,
    ) -> tuple[str, Any]:
        if self.model is None or self.tokenizer is None:
            await self.initialize(system_instruction=self.system_instruction)
        from ..research.latent_communication import LatentAgentOrchestrator

        if self._latent_orchestrator is None:
            self._latent_orchestrator = LatentAgentOrchestrator(
                self.model,
                self.tokenizer,
                latent_steps=latent_steps,
                device=self.device,
            )
        return await asyncio.wait_for(
            self._latent_orchestrator.run_pipeline(task, max_new_tokens=max_new_tokens),
            timeout=self.timeout,
        )
