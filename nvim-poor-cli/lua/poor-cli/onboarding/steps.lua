-- poor-cli/onboarding/steps.lua
-- Linear step chain for first-run setup. Each step descriptor:
--   { id, kind = "info"|"select"|"input"|"dynamic"|"commit", title, items?, default?, apply?, skip? }
--   • "select"   — vim.ui.select over items(state). apply(choice, state).
--   • "input"    — vim.ui.input with prompt. apply(value, state, done_cb).
--   • "info"     — small info float; <CR> advances.
--   • "dynamic"  — callable step that manages its own async completion.
--   • "commit"   — final RPC batch save.

local config = require("poor-cli.config")
local rpc = require("poor-cli.rpc")

local M = {}

-- All provider adapters poor-cli ships. Kept in sync with
-- poor_cli/providers/provider_factory.py::ProviderFactory.list_providers.
M.ALL_PROVIDERS = {
    "gemini", "openai", "anthropic", "openrouter", "litellm",
    "ollama", "lmstudio", "llama_server", "vllm", "sglang", "hf_tgi", "hf_local",
}

local function notify(msg, level)
    require("poor-cli.notify").notify("[poor-cli] " .. msg, level)
end

local function provider_labels(state)
    local pd = state.provider_data or {}
    local items, ids = {}, {}
    for _, name in ipairs(M.ALL_PROVIDERS) do
        local info = pd[name] or {}
        local status = info.statusLabel or "unknown"
        table.insert(items, string.format("%-14s [%s]", name, status))
        table.insert(ids, name)
    end
    return items, ids
end

local function model_labels(state)
    local pd = state.provider_data or {}
    local info = pd[state.choices.provider or ""] or {}
    local models = info.models or {}
    local tiers = info.modelTiers or {}
    local items, ids = {}, {}
    for _, m in ipairs(models) do
        local t = tiers[m] or {}
        local cost = ""
        if t.cost1kIn and t.cost1kIn > 0 then
            cost = string.format("  $%.5f/1k", t.cost1kIn)
        elseif t.tier == "private" then
            cost = "  (free, local)"
        end
        local ctx = t.contextWindow and t.contextWindow > 0
            and string.format("  ctx:%dk", t.contextWindow / 1000) or ""
        table.insert(items, string.format("%s [%s]%s%s", m, t.tier or "?", cost, ctx))
        table.insert(ids, m)
    end
    return items, ids
end

-- ───────────────── steps ─────────────────

M.STEPS = {
    {
        id = "welcome",
        kind = "info",
        title = "welcome",
        body = {
            "poor-cli is an AI coding assistant that runs inside Neovim.",
            "It connects to LLM providers (OpenAI, Anthropic, Gemini, Ollama, OpenRouter)",
            "and gives you inline completions, chat, and agentic coding tools.",
            "",
            "This wizard will configure your essentials.",
            "You can re-run it anytime with :PoorCLIHelp onboarding.",
        },
    },
    {
        id = "provider",
        kind = "select",
        title = "provider",
        prompt = "Select provider:",
        items = function(state) return provider_labels(state) end,
        apply = function(state, _, idx, ids)
            local picked = ids[idx]
            if picked ~= state.choices.provider then
                state.choices.api_key = nil
                state.choices.model = nil
            end
            state.choices.provider = picked
        end,
    },
    {
        id = "api_key",
        kind = "dynamic",
        title = "api key",
        skip = function(state)
            return state.choices.provider == "ollama"
                or state.choices.provider == "lmstudio"
                or state.choices.provider == "llama_server"
                or state.choices.provider == "vllm"
                or state.choices.provider == "sglang"
                or state.choices.provider == "hf_local"
        end,
        run = function(state, advance, cancel)
            local prov = state.choices.provider or "?"
            vim.ui.input({ prompt = "API key for " .. prov .. ": " }, function(key)
                if key == nil then cancel(); return end
                if key == "" then
                    notify("key empty — skipped", vim.log.levels.WARN)
                    advance(); return
                end
                notify("validating key...", vim.log.levels.INFO)
                rpc.request("poor-cli/testApiKey", { provider = prov, apiKey = key }, function(result, err)
                    vim.schedule(function()
                        if err then
                            notify("validation error: " .. rpc.format_error(err) .. " — retrying", vim.log.levels.ERROR)
                            M.STEPS[3].run(state, advance, cancel); return
                        end
                        if result and result.valid then
                            state.choices.api_key = key
                            notify("key valid", vim.log.levels.INFO)
                            advance()
                        else
                            notify("invalid key: " .. (result and result.error or "unknown"), vim.log.levels.ERROR)
                            M.STEPS[3].run(state, advance, cancel)
                        end
                    end)
                end)
            end)
        end,
    },
    {
        id = "model",
        kind = "select",
        title = "model",
        prompt = "Select model:",
        skip = function(state)
            local pd = state.provider_data or {}
            local info = pd[state.choices.provider or ""] or {}
            return not info.models or #info.models == 0
        end,
        items = function(state) return model_labels(state) end,
        apply = function(state, _, idx, ids) state.choices.model = ids[idx] end,
    },
    {
        id = "permission_mode",
        kind = "select",
        title = "permission mode",
        prompt = "How autonomous should the AI be?",
        items = function()
            return {
                "Cautious  — ask before risky operations (recommended)",
                "Balanced  — auto-approve edits, ask for destructive ops",
                "Autonomous — full auto, no prompts",
            }, { "default", "acceptEdits", "bypassPermissions" }
        end,
        apply = function(state, _, idx, ids) state.choices.permission_mode = ids[idx] end,
    },
    {
        id = "economy",
        kind = "select",
        title = "economy preset",
        prompt = "How should poor-cli manage token costs?",
        items = function()
            return {
                "frugal   — max cost savings, aggressive compression",
                "balanced — good balance of cost and quality (recommended)",
                "quality  — no cost optimizations, max quality",
            }, { "frugal", "balanced", "quality" }
        end,
        apply = function(state, _, idx, ids) state.choices.economy_preset = ids[idx] end,
    },
    {
        id = "budget",
        kind = "select",
        title = "cost budget",
        prompt = "Session spending limit:",
        items = function()
            return {
                "Quick question  — $0.01/session",
                "Code review     — $0.10/session",
                "Deep refactor   — $0.50/session",
                "Unlimited       — no limit",
            }, { "quick_question", "code_review", "deep_refactor", "unlimited" }
        end,
        apply = function(state, _, idx, ids) state.choices.budget = ids[idx] end,
    },
    {
        id = "summary",
        kind = "info",
        title = "complete",
        body = function(state)
            local c = state.choices
            local key = c.api_key
                and (string.sub(c.api_key, 1, 4) .. "..." .. string.sub(c.api_key, -4))
                or "(not set)"
            return {
                "Review your choices:",
                "",
                "  provider:    " .. (c.provider or "(not set)"),
                "  api key:     " .. key,
                "  model:       " .. (c.model or "(auto)"),
                "  permission:  " .. (c.permission_mode or "default"),
                "  economy:     " .. (c.economy_preset or "balanced"),
                "  budget:      " .. (c.budget or "unlimited"),
                "",
                "Press <CR> to save, q to cancel.",
            }
        end,
    },
    {
        id = "commit",
        kind = "commit",
        run = function(state, advance, cancel)
            local c = state.choices

            local function save_config()
                local pending = 0
                local errors = {}
                local function on_done(_, err)
                    vim.schedule(function()
                        if err then table.insert(errors, rpc.format_error(err)) end
                        pending = pending - 1
                        if pending <= 0 then
                            if #errors > 0 then
                                notify("save errors: " .. table.concat(errors, "; "), vim.log.levels.ERROR)
                            else
                                notify("onboarding complete!", vim.log.levels.INFO)
                            end
                            advance()
                        end
                    end)
                end

                if c.api_key and c.provider then
                    pending = pending + 1
                    rpc.request("poor-cli/setApiKey", {
                        provider = c.provider, apiKey = c.api_key,
                        persist = true, reloadActiveProvider = true,
                    }, on_done)
                end
                if c.provider then
                    pending = pending + 1
                    rpc.request("poor-cli/setConfig", { keyPath = "model.provider", value = c.provider }, on_done)
                end
                if c.model then
                    pending = pending + 1
                    rpc.request("poor-cli/setConfig", { keyPath = "model.model_name", value = c.model }, on_done)
                end
                pending = pending + 1
                rpc.request("poor-cli/setConfig",
                    { keyPath = "security.permission_mode", value = c.permission_mode or "default" }, on_done)
                pending = pending + 1
                rpc.request("poor-cli/setEconomyPreset", { preset = c.economy_preset or "balanced" }, on_done)
                if c.budget and c.budget ~= "unlimited" then
                    pending = pending + 1
                    rpc.request("poor-cli/applyBudgetTemplate", { template = c.budget }, on_done)
                end

                if pending == 0 then
                    notify("onboarding complete!", vim.log.levels.INFO)
                    advance()
                end
            end

            rpc.initialize(function(_, err)
                vim.schedule(function()
                    if err then
                        notify("server re-init failed: " .. rpc.format_error(err)
                            .. " — saving local prefs only", vim.log.levels.WARN)
                        advance()
                        return
                    end
                    save_config()
                end)
            end, { provider = c.provider, model = c.model })
        end,
    },
}

-- Tour variant: a much shorter demo flow that surfaces the 5 key features.
M.TOUR_STEPS = {
    {
        id = "tour_welcome",
        kind = "info",
        title = "tour",
        body = {
            "Quick tour of poor-cli core features.",
            "We'll walk through: chat, inline completion, diff review,",
            "checkpoints, and rollback.",
        },
    },
    {
        id = "tour_chat",
        kind = "info",
        title = "chat",
        body = {
            "Chat: :PoorCLIChat toggle opens the chat panel.",
            "Use it for explanations, refactors, and general Q&A.",
        },
    },
    {
        id = "tour_inline",
        kind = "info",
        title = "inline completion",
        body = {
            "Inline completion: in insert mode press <C-Space> to trigger",
            "ghost text. <Tab> accepts, <M-]>/<M-[> cycles alternates.",
        },
    },
    {
        id = "tour_diff",
        kind = "info",
        title = "diff review",
        body = {
            "Diff review: :PoorCLIDiff review opens the 2-pane review panel.",
            "ga accepts a hunk, gr rejects, gc regenerates.",
        },
    },
    {
        id = "tour_checkpoints",
        kind = "info",
        title = "checkpoints",
        body = {
            "Checkpoints: poor-cli snapshots your files before AI edits.",
            "Rollback anytime from :PoorCLIPanel toggle checkpoints.",
        },
    },
}

return M
