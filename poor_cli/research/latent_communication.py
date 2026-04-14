"""
Latent-space inter-agent communication prototype.

Implements LatentMAS-style hidden-state passing between agents,
replacing text round-trips with direct last-layer hidden state transfer
via KV cache prepending. Training-free — uses analytically computed
realignment matrix from model's own embedding weights.

Requirements:
  - torch, transformers (HuggingFace)
  - open-weights model (Qwen2.5, LLaMA, Mistral, etc.)
  - GPU with sufficient VRAM for the model in bf16/fp16

References:
  - LatentMAS: https://arxiv.org/abs/2511.20639
  - Interlat: https://arxiv.org/abs/2511.09149
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False


def _no_grad(func=None):
    if HAS_TORCH:
        return torch.no_grad()(func) if func is not None else torch.no_grad()
    if func is not None:
        return func
    return lambda wrapped: wrapped

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


def check_deps():
    if not HAS_TORCH:
        raise ImportError("torch required: pip install torch")
    if not HAS_TRANSFORMERS:
        raise ImportError("transformers required: pip install transformers")


@dataclass
class LatentMessage:
    """Hidden-state message passed between agents."""
    hidden_states: Any  # torch.Tensor [1, D] — last-layer hidden at final position
    kv_cache: Any  # past_key_values tuple from HF model
    source_role: str
    latent_steps: int  # how many latent reasoning steps were run
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LatentBenchmark:
    """Timing/token stats for a latent vs text run."""
    mode: str  # "latent" or "text"
    wall_time_s: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latent_steps: int = 0


class RealignmentMatrix:
    """Computes and caches the output->input embedding realignment matrix.

    Maps last-layer hidden states (output/logit space) back to input
    embedding space for feeding as inputs_embeds. Closed-form solution:
        R = (W_out^T W_out + λI)^{-1} W_out^T W_in
    """

    def __init__(self, model: Any, reg: float = 1e-4):
        check_deps()
        w_in = model.get_input_embeddings().weight.detach().float()  # [V, D]
        w_out = model.get_output_embeddings().weight.detach().float()  # [V, D]
        gram = w_out.T @ w_out + reg * torch.eye(w_out.shape[1], device=w_out.device)
        self.matrix = torch.linalg.solve(gram, w_out.T @ w_in).to(model.dtype)  # [D, D]
        self.target_norm = w_in.norm(dim=-1).mean().item()

    def apply(self, hidden: "torch.Tensor") -> "torch.Tensor":
        """Realign hidden state and normalize to input embedding scale."""
        projected = hidden.float() @ self.matrix.float()
        norm = projected.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return (projected * self.target_norm / norm).to(hidden.dtype)


class LatentAgent:
    """Agent that communicates via hidden states instead of text.

    Uses LatentMAS approach: run forward passes to accumulate
    'latent reasoning steps' in the KV cache without decoding tokens.
    Only the final agent in a pipeline decodes text output.
    """

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        role: str,
        realign: Optional[RealignmentMatrix] = None,
        latent_steps: int = 20,
        device: str = "cuda",
    ):
        check_deps()
        self.model = model
        self.tokenizer = tokenizer
        self.role = role
        self.realign = realign or RealignmentMatrix(model)
        self.latent_steps = latent_steps
        self.device = device

    def _tokenize(self, text: str) -> "torch.Tensor":
        return self.tokenizer(text, return_tensors="pt").input_ids.to(self.device)

    @_no_grad
    def forward_latent(
        self,
        prompt: str,
        prior_kv: Any = None,
        prior_hidden: Optional["torch.Tensor"] = None,
    ) -> LatentMessage:
        """Run prompt through model, accumulate latent steps, return hidden state + KV cache.

        Does NOT decode any text tokens. The 'reasoning' is entirely
        encoded in the KV cache and final hidden state.
        """
        input_ids = self._tokenize(prompt)
        # if we have prior hidden state from another agent, prepend as inputs_embeds
        if prior_hidden is not None:
            realigned = self.realign.apply(prior_hidden).unsqueeze(1)  # [1, 1, D]
            prompt_embeds = self.model.get_input_embeddings()(input_ids)  # [1, seq, D]
            inputs_embeds = torch.cat([realigned, prompt_embeds], dim=1)  # [1, 1+seq, D]
            out = self.model(
                inputs_embeds=inputs_embeds,
                past_key_values=prior_kv,
                output_hidden_states=True,
                use_cache=True,
                return_dict=True,
            )
        else:
            out = self.model(
                input_ids=input_ids,
                past_key_values=prior_kv,
                output_hidden_states=True,
                use_cache=True,
                return_dict=True,
            )
        kv = out.past_key_values
        hidden = out.hidden_states[-1][:, -1, :]  # [1, D] last layer, last pos
        # latent reasoning loop: feed hidden state back without decoding
        for _ in range(self.latent_steps):
            realigned = self.realign.apply(hidden).unsqueeze(1)  # [1, 1, D]
            out = self.model(
                inputs_embeds=realigned,
                past_key_values=kv,
                output_hidden_states=True,
                use_cache=True,
                return_dict=True,
            )
            kv = out.past_key_values
            hidden = out.hidden_states[-1][:, -1, :]
        return LatentMessage(
            hidden_states=hidden,
            kv_cache=kv,
            source_role=self.role,
            latent_steps=self.latent_steps,
        )

    @_no_grad
    def generate_from_latent(
        self,
        prompt: str,
        latent_msg: Optional[LatentMessage] = None,
        max_new_tokens: int = 512,
    ) -> Tuple[str, int]:
        """Generate text output, optionally conditioned on latent context from another agent.

        This is the 'Judger' — the final agent that actually decodes text.
        Returns (text, output_token_count).
        """
        input_ids = self._tokenize(prompt)
        kv = latent_msg.kv_cache if latent_msg else None
        if latent_msg and latent_msg.hidden_states is not None:
            realigned = self.realign.apply(latent_msg.hidden_states).unsqueeze(1)
            prompt_embeds = self.model.get_input_embeddings()(input_ids)
            inputs_embeds = torch.cat([realigned, prompt_embeds], dim=1)
            out = self.model.generate(
                inputs_embeds=inputs_embeds,
                past_key_values=kv,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        else:
            out = self.model.generate(
                input_ids=input_ids,
                past_key_values=kv,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        # decode only the new tokens (skip input length)
        new_tokens = out[0][input_ids.shape[1]:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return text, len(new_tokens)


class LatentAgentOrchestrator:
    """Coordinates agents using latent communication.

    Implements the LatentMAS sequential pipeline:
    Planner -> Critic -> Refiner -> Judger
    First 3 agents produce zero decoded tokens. Only Judger outputs text.
    """

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        latent_steps: int = 20,
        device: str = "cuda",
    ):
        check_deps()
        self.realign = RealignmentMatrix(model)
        self.planner = LatentAgent(model, tokenizer, "planner", self.realign, latent_steps, device)
        self.critic = LatentAgent(model, tokenizer, "critic", self.realign, latent_steps, device)
        self.refiner = LatentAgent(model, tokenizer, "refiner", self.realign, latent_steps, device)
        self.judger = LatentAgent(model, tokenizer, "judger", self.realign, latent_steps, device)
        self.model = model
        self.tokenizer = tokenizer
        self.device = device

    async def run_pipeline(
        self,
        task: str,
        max_new_tokens: int = 512,
    ) -> Tuple[str, LatentBenchmark]:
        """Run full planner->critic->refiner->judger pipeline via latent states."""
        t0 = time.monotonic()
        # planner: analyze task in latent space
        plan_msg = self.planner.forward_latent(f"Plan a solution for: {task}")
        # critic: review plan in latent space
        critic_msg = self.critic.forward_latent(
            "Review and critique the plan:",
            prior_kv=plan_msg.kv_cache,
            prior_hidden=plan_msg.hidden_states,
        )
        # refiner: improve based on critique
        refine_msg = self.refiner.forward_latent(
            "Refine the plan based on critique:",
            prior_kv=critic_msg.kv_cache,
            prior_hidden=critic_msg.hidden_states,
        )
        # judger: decode final answer
        text, out_tokens = self.judger.generate_from_latent(
            f"Provide the final answer for: {task}",
            latent_msg=refine_msg,
            max_new_tokens=max_new_tokens,
        )
        elapsed = time.monotonic() - t0
        input_ids = self.tokenizer(task, return_tensors="pt").input_ids
        bench = LatentBenchmark(
            mode="latent",
            wall_time_s=elapsed,
            input_tokens=len(input_ids[0]),
            output_tokens=out_tokens,
            total_tokens=len(input_ids[0]) + out_tokens,
            latent_steps=self.planner.latent_steps * 3,  # 3 latent agents
        )
        return text, bench

    async def run_text_baseline(
        self,
        task: str,
        max_new_tokens: int = 512,
    ) -> Tuple[str, LatentBenchmark]:
        """Run same pipeline but with full text round-trips (baseline for comparison)."""
        t0 = time.monotonic()
        total_out = 0
        total_in = 0
        roles = [
            ("planner", f"Plan a solution for: {task}"),
            ("critic", "Review and critique the following plan:\n{prev}"),
            ("refiner", "Refine this plan based on the critique:\n{prev}"),
            ("judger", "Provide the final answer based on this refined plan:\n{prev}"),
        ]
        prev_text = ""
        for role, prompt_tmpl in roles:
            prompt = prompt_tmpl.format(prev=prev_text) if "{prev}" in prompt_tmpl else prompt_tmpl
            input_ids = self.tokenizer(prompt, return_tensors="pt").input_ids.to(self.device)
            total_in += len(input_ids[0])
            with torch.no_grad():
                out = self.model.generate(
                    input_ids=input_ids,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                )
            new_tokens = out[0][input_ids.shape[1]:]
            total_out += len(new_tokens)
            prev_text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        elapsed = time.monotonic() - t0
        return prev_text, LatentBenchmark(
            mode="text",
            wall_time_s=elapsed,
            input_tokens=total_in,
            output_tokens=total_out,
            total_tokens=total_in + total_out,
        )


class ArchitectLatentBridge:
    """Bridge for poor-cli's architect->editor flow using latent communication.

    Drop-in enhancement for ArchitectMode: instead of passing the plan
    as text to the editor, pass the architect's hidden states directly.
    Requires both architect and editor to use the same local model.
    """

    def __init__(self, model: Any, tokenizer: Any, device: str = "cuda"):
        check_deps()
        self.realign = RealignmentMatrix(model)
        self.architect = LatentAgent(model, tokenizer, "architect", self.realign, latent_steps=30, device=device)
        self.editor = LatentAgent(model, tokenizer, "editor", self.realign, latent_steps=0, device=device)

    async def architect_to_editor(
        self,
        task: str,
        max_new_tokens: int = 1024,
    ) -> Tuple[str, LatentBenchmark]:
        """Architect reasons in latent space, editor decodes the implementation."""
        t0 = time.monotonic()
        plan_msg = self.architect.forward_latent(
            f"You are a software architect. Plan the implementation for: {task}"
        )
        result, out_tokens = self.editor.generate_from_latent(
            "You are a code editor. Implement the plan:",
            latent_msg=plan_msg,
            max_new_tokens=max_new_tokens,
        )
        elapsed = time.monotonic() - t0
        input_ids = self.architect.tokenizer(task, return_tensors="pt").input_ids
        return result, LatentBenchmark(
            mode="latent",
            wall_time_s=elapsed,
            input_tokens=len(input_ids[0]),
            output_tokens=out_tokens,
            total_tokens=len(input_ids[0]) + out_tokens,
            latent_steps=self.architect.latent_steps,
        )


def load_model(
    model_name: str = "Qwen/Qwen2.5-3B",
    device: str = "cuda",
    dtype: str = "bfloat16",
) -> Tuple[Any, Any]:
    """Load an open-weights model for latent communication experiments.

    Recommended models (tested with LatentMAS architecture):
      - Qwen/Qwen2.5-3B (fits 24GB GPU)
      - Qwen/Qwen2.5-7B (fits 24GB GPU in bf16)
      - Qwen/Qwen3-4B (fits 24GB GPU)
      - meta-llama/Llama-3.2-3B (fits 24GB GPU)

    Larger models need multi-GPU or quantization.
    """
    check_deps()
    dt = getattr(torch, dtype)
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=dt,
        device_map=device,
        trust_remote_code=True,
    )
    model.eval()
    return model, tokenizer


def is_latent_compatible() -> Dict[str, Any]:
    """Check if the current environment supports latent communication."""
    result = {
        "torch_available": HAS_TORCH,
        "transformers_available": HAS_TRANSFORMERS,
        "cuda_available": HAS_TORCH and torch.cuda.is_available(),
        "mps_available": HAS_TORCH and torch.backends.mps.is_available(),
        "gpu_count": torch.cuda.device_count() if HAS_TORCH and torch.cuda.is_available() else 0,
        "feasible": False,
        "reason": "",
    }
    if not result["torch_available"]:
        result["reason"] = "torch not installed"
    elif not result["transformers_available"]:
        result["reason"] = "transformers not installed"
    elif not result["cuda_available"] and not result["mps_available"]:
        result["reason"] = "no GPU available (CUDA or MPS required)"
    else:
        result["feasible"] = True
        result["reason"] = "environment supports latent communication"
    return result
