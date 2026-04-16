-- poor-cli/ux.lua
-- opt-in UX feature dispatcher. each feature is a submodule under ux/
-- and installs itself only when its config flag is true.

local M = {}

local FEATURES = {
    command_palette      = "poor-cli.ux.palette",
    streaming_indicator  = "poor-cli.ux.streaming",
    auto_onboarding      = "poor-cli.ux.auto_onboarding",
    panels_bulk          = "poor-cli.ux.panels_bulk",
    inline_cycle_hint    = "poor-cli.ux.inline_cycle",
    cost_lualine_auto    = "poor-cli.ux.cost_lualine",
    diff_accept_all      = "poor-cli.ux.diff_accept_all",
    context_remove_files = "poor-cli.ux.context_remove",
    home_nav             = "poor-cli.ux.home",
    provider_cost_preview = "poor-cli.ux.provider_cost",
    inline_status_lualine = "poor-cli.ux.inline_status",
    chat_history_search  = "poor-cli.ux.history_search",
    completion_reason    = "poor-cli.ux.completion_reason",
    health_actions       = "poor-cli.ux.health_actions",
}

function M.setup()
    local ux = require("poor-cli.config").get("ux") or {}
    -- fast path: if no flag is enabled, skip the dispatch loop entirely
    local any = false
    for _, v in pairs(ux) do if v then any = true; break end end
    if not any then return end
    for flag, modname in pairs(FEATURES) do
        if ux[flag] then
            local ok, mod = pcall(require, modname)
            if ok and type(mod.install) == "function" then
                pcall(mod.install)
            end
        end
    end
end

M._features = FEATURES -- test hook

return M
