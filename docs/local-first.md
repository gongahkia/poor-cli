# Local First

Phase 3 targets Linux/CUDA local model runs through vLLM, SGLang, or Ollama.

## Setup

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct
```

The setup script creates:

- `.poor-cli/local-cuda-venv/`
- `.poor-cli/local-cuda.env`
- `.poor-cli/local-cuda-run.sh`

It requires Linux and `nvidia-smi` by default. For CI or syntax validation only, pass `--skip-cuda-check` and set `POOR_CLI_ALLOW_NON_LINUX=1`.

## Engines

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm
scripts/setup-linux-cuda.sh --yes --engine sglang
scripts/setup-linux-cuda.sh --yes --engine ollama --skip-engine-install
```

The script installs `vllm` or `sglang[all]` into the local venv when selected. Ollama is expected to be installed as a system service or binary.

## Cache Controls

The setup script enables provider-native prefix caching by default where the engine exposes it:

```sh
scripts/setup-linux-cuda.sh --yes --engine vllm --prefix-cache-hash-algo sha256 --kv-cache-dtype fp8_e5m2
scripts/setup-linux-cuda.sh --yes --engine sglang --kv-cache-dtype fp8_e5m2
scripts/setup-linux-cuda.sh --yes --engine vllm --no-prefix-cache
scripts/setup-linux-cuda.sh --yes --engine sglang --no-prefix-cache
```

For vLLM, `--prefix-cache` writes `--enable-prefix-caching` and `--prefix-caching-hash-algo` into `.poor-cli/local-cuda-run.sh`; `--no-prefix-cache` writes `--no-enable-prefix-caching`.
For SGLang, prefix cache is the radix cache path; `--no-prefix-cache` writes `--disable-radix-cache`.
For both engines, `--kv-cache-dtype` is passed through when set to anything other than `auto`.

## Replay

Record/replay remains the control plane. A local model run should still produce a normal run store, and `poor-cli --offline replay <run_id> --verify` should verify without credentials.
