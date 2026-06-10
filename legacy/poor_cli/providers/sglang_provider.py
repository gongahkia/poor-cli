"""SGLang OpenAI-compatible local text provider."""

from .capability import PROVIDER_CAPABILITIES
from .vllm_provider import VLLMProvider


class SGLangProvider(VLLMProvider):
    provider_key = "sglang"
    provider_label = "SGLang"
    default_base_url = "http://localhost:30000/v1"
    auth_env_var = "SGLANG_API_KEY"
    capabilities = PROVIDER_CAPABILITIES["sglang"]
