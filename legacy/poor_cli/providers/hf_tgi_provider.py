"""Hugging Face TGI OpenAI-compatible local text provider."""

from .capability import PROVIDER_CAPABILITIES
from .vllm_provider import VLLMProvider


class HFTGIProvider(VLLMProvider):
    provider_key = "hf_tgi"
    provider_label = "HF TGI"
    default_base_url = "http://localhost:3000/v1"
    auth_env_var = "HF_TGI_API_KEY"
    capabilities = PROVIDER_CAPABILITIES["hf_tgi"]
