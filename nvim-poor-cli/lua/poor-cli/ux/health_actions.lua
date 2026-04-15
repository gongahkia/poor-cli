-- poor-cli/ux/health_actions.lua
-- Append an "Actions" section to :checkhealth poor-cli with runnable
-- commands the user can copy to fix common issues.

local M = {}

local function any_key()
    for _, e in ipairs({ "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY" }) do
        if vim.env[e] and vim.env[e] ~= "" then return true end
    end
    return false
end

function M.install()
    local health_mod = require("poor-cli.health")
    if M._installed then return end
    M._installed = true
    local orig_check = health_mod.check
    health_mod.check = function(...)
        local ret = orig_check(...)
        local health = vim.health or require("health")
        local start = health.start or health.report_start
        local info = health.info or health.report_info
        local warn = health.warn or health.report_warn

        start("poor-cli actions")
        info("Run :PoorCLIOnboarding to configure a provider and API key.")
        info("Run :PoorCLIStart to start the backend server.")
        info("Run :PoorCLIStatus to inspect current RPC state.")
        info("Run :PoorCLIPalette (if ux.command_palette enabled) to browse commands.")
        info("Run :PoorCLIHome (if ux.home_nav enabled) to close aux panels.")
        if not any_key() then
            warn("No API key detected — :PoorCLIOnboarding will guide you through setup.")
        end
        local rpc = require("poor-cli.rpc")
        if not rpc.is_running() then
            warn("Server not running — :PoorCLIStart to start it.")
        end
        return ret
    end
end

return M
