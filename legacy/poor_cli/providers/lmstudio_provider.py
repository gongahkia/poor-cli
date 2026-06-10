"""LM Studio OpenAI-compatible local text provider."""

from .capability import PROVIDER_CAPABILITIES
from .vllm_provider import VLLMProvider


class LMStudioProvider(VLLMProvider):
    provider_key = "lmstudio"
    provider_label = "LM Studio"
    default_base_url = "http://localhost:1234/v1"
    auth_env_var = "LMSTUDIO_API_KEY"
    capabilities = PROVIDER_CAPABILITIES["lmstudio"]
