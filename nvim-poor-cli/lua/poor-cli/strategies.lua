-- poor-cli/strategies.lua
-- Runtime UI for swap-able feature strategies (MH7 reranker, CB3 adaptive
-- tool scoring). Reads/writes via poor-cli/{getStrategies,setStrategy} RPCs.
-- The backend persists to .poor-cli/strategies.json.

local M = {}

M._cached = nil

local function fetch(cb)
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/getStrategies", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] getStrategies: " .. rpc.format_error(err), vim.log.levels.ERROR)
                if cb then cb(nil, err) end
                return
            end
            M._cached = result
            if cb then cb(result) end
        end)
    end)
end

local function apply(name, value, cb)
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/setStrategy", { name = name, value = value }, function(result, err)
        vim.schedule(function()
            if err or (result and result.error) then
                local msg = err and rpc.format_error(err) or (result and result.error) or "unknown"
                require("poor-cli.notify").notify("[poor-cli] setStrategy: " .. tostring(msg), vim.log.levels.ERROR)
                if cb then cb(nil, msg) end
                return
            end
            M._cached = { strategies = (result or {}).strategies or {} }
            require("poor-cli.notify").notify(string.format("[poor-cli] %s = %s", name, tostring(value)), vim.log.levels.INFO)
            if cb then cb(result) end
        end)
    end)
end

function M.show()
    fetch(function(result)
        if not result then return end
        local s = result.strategies or {}
        local lines = {
            "# poor-cli strategies",
            "",
            string.format("- memory_reranker_strategy: %s", tostring(s.memory_reranker_strategy)),
            string.format("- memory_reranker_cross_encoder_model: %s", tostring(s.memory_reranker_cross_encoder_model)),
            string.format("- adaptive_tool_scoring: %s", tostring(s.adaptive_tool_scoring)),
            "",
            "commands:",
            "  :PoorCLIWorkflow reranker [mmr|cross_encoder|score_order]",
            "  :PoorCLIWorkflow adaptive-pruning [auto|on|off]",
            "  :PoorCLIWorkflow strategies   (this)",
        }
        require("poor-cli.notify").notify(table.concat(lines, "\n"), vim.log.levels.INFO)
    end)
end

local function cycle_next(current, choices)
    for i, v in ipairs(choices) do
        if v == current then return choices[(i % #choices) + 1] end
    end
    return choices[1]
end

function M.set_reranker(arg)
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/getStrategies", {}, function(result, err)
        vim.schedule(function()
            if err then return end
            local current = (result.strategies or {}).memory_reranker_strategy or "mmr"
            local choices = (result.choices or {}).memory_reranker_strategy or { "mmr", "cross_encoder", "score_order" }
            local value = arg
            if value == nil or value == "" then value = cycle_next(current, choices) end
            apply("memory_reranker_strategy", value)
        end)
    end)
end

function M.set_adaptive(arg)
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/getStrategies", {}, function(result, err)
        vim.schedule(function()
            if err then return end
            local current = (result.strategies or {}).adaptive_tool_scoring or "auto"
            local choices = (result.choices or {}).adaptive_tool_scoring or { "auto", "on", "off" }
            local value = arg
            if value == nil or value == "" then value = cycle_next(current, choices) end
            apply("adaptive_tool_scoring", value)
        end)
    end)
end

-- setup() intentionally removed: strategies are reached via the workflow
-- dispatcher (`:PoorCLIWorkflow strategies|reranker|adaptive-pruning`).
-- M.show(), M.set_reranker(), M.set_adaptive() remain as the module API.
function M.setup() end

M._cycle_next = cycle_next -- test hook

return M
