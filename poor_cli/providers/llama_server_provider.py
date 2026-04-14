"""llama-server OpenAI-compatible local text provider."""

from .capability import PROVIDER_CAPABILITIES
from .vllm_provider import VLLMProvider


class LlamaServerProvider(VLLMProvider):
    provider_key = "llama_server"
    provider_label = "llama-server"
    default_base_url = "http://localhost:8080/v1"
    auth_env_var = "LLAMA_SERVER_API_KEY"
    capabilities = PROVIDER_CAPABILITIES["llama_server"]
