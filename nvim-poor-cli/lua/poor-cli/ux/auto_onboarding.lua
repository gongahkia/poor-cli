-- poor-cli/ux/auto_onboarding.lua
-- surfaces onboarding when no API key is detected for the selected provider.
-- runs once per session, 2s after setup.

local M = {}

local function any_known_key()
    local envs = {
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "OPENROUTER_API_KEY", "HF_API_TOKEN", "HUGGINGFACE_API_KEY",
    }
    for _, e in ipairs(envs) do
        if vim.env[e] and vim.env[e] ~= "" then return true end
    end
    return false
end

function M.check()
    if any_known_key() then return false end
    local notify = require("poor-cli.notify")
    notify.notify(
        "[poor-cli] no API key detected. Run :PoorCLIHelp onboarding to configure a provider.",
        vim.log.levels.WARN
    )
    return true
end

function M.install()
    vim.defer_fn(function() pcall(M.check) end, 2000)
end

return M
