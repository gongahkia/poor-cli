-- poor-cli/ux/provider_cost.lua
-- :PoorCLIProviderCompare — side-by-side table of provider/model costs,
-- with Δ (delta) vs currently-active provider/model.

local M = {}

local function parse_price(label)
    local cin, cout = label:match("^%$([%d%.]+)/%$([%d%.]+)")
    if not cin then return nil, nil end
    return tonumber(cin), tonumber(cout)
end

function M.build_rows(providers, current)
    local pp = require("poor-cli.provider_picker")
    local items = pp.build_items(providers, current)
    local cur_in, cur_out
    for _, it in ipairs(items) do
        if current and it.data.provider == current.name and it.data.model == current.model then
            local label = it.label:match("(%$[%d%.]+/%$[%d%.]+)") or ""
            cur_in, cur_out = parse_price(label)
            break
        end
    end
    local rows = {}
    for _, it in ipairs(items) do
        local label = it.label:match("(%$[%d%.]+/%$[%d%.]+)") or ""
        local cin, cout = parse_price(label)
        local delta = ""
        if cin and cout and cur_in and cur_out then
            local di = cin - cur_in
            local dot = cout - cur_out
            delta = string.format(" Δ $%+.4g / $%+.4g", di, dot)
        end
        table.insert(rows, string.format("%-12s %-40s %-18s%s",
            it.data.provider, it.data.model, label ~= "" and label or "(n/a)", delta))
    end
    return rows
end

function M.open()
    local rpc = require("poor-cli.rpc")
    rpc.request("poor-cli/listProviders", {}, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] listProviders: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end
            rpc.request("poor-cli/getProviderInfo", {}, function(curr, _)
                vim.schedule(function()
                    local current = type(curr) == "table" and { name = curr.name, model = curr.model } or nil
                    local rows = M.build_rows(result or {}, current)
                    local buf = vim.api.nvim_create_buf(false, true)
                    vim.bo[buf].buftype = "nofile"
                    vim.bo[buf].bufhidden = "wipe"
                    vim.bo[buf].filetype = "markdown"
                    vim.api.nvim_buf_set_name(buf, "[poor-cli provider compare]")
                    local header = {
                        "# Provider cost compare",
                        current and ("current: " .. current.name .. " / " .. current.model) or "current: unknown",
                        "", string.format("%-12s %-40s %-18s %s", "provider", "model", "price ($/1k in/out)", "Δ vs current"),
                        string.rep("-", 90),
                    }
                    for _, r in ipairs(rows) do table.insert(header, r) end
                    vim.api.nvim_buf_set_lines(buf, 0, -1, false, header)
                    vim.cmd("botright split")
                    vim.api.nvim_win_set_buf(0, buf)
                    vim.keymap.set("n", "q", ":close<CR>", { buffer = buf, silent = true, nowait = true })
                end)
            end)
        end)
    end)
end

function M.install()
    pcall(vim.api.nvim_del_user_command, "PoorCLIProviderCompare")
    vim.api.nvim_create_user_command("PoorCLIProviderCompare", function() M.open() end, { desc = "Compare provider/model costs vs current" })
end

return M
