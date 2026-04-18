local M = {}

function M.extend(deps)
    local spec = deps.spec
    local rpc = deps.rpc
    local notify = deps.notify
    local open_scratch = deps.open_scratch
    local parse_audit_export_args = deps.parse_audit_export_args

    spec.extend("cost", {
        verbs = {
            ["audit-export"] = function(fargs)
                local raw = table.concat(fargs, " ")
                rpc.request("audit/exportRange", parse_audit_export_args(raw), function(result, err) vim.schedule(function()
                    if err then notify("Audit export failed: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
                    if type(result) == "table" and result.path then
                        notify("Exported " .. tostring(result.count or 0) .. " audit events to " .. tostring(result.path), vim.log.levels.INFO)
                    elseif type(result) == "table" and result.jsonl then
                        open_scratch("[poor-cli audit export]", tostring(result.jsonl), "json")
                    end
                end) end)
            end,
        },
    })

    spec.extend("cost", {
        verbs = {
            dashboard = function() require("poor-cli.panels.cost_dashboard").open() end,
            estimate = function(fargs)
                local msg = table.concat(fargs, " ")
                if msg == "" then msg = "hello" end
                local result, err = rpc.estimate_cost({ message = msg }, 10000)
                if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                local r = result or {}
                notify(("estimate: ~%d in / ~%d out tokens, ~$%.4f"):format(
                    r.estimatedInputTokens or 0, r.estimatedOutputTokens or 0, r.estimatedCostUSD or 0
                ), vim.log.levels.INFO)
            end,
        },
    })
end

return M
