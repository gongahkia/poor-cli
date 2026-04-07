local rpc = require("poor-cli.rpc")
local M = {}

local function open_scratch(title, content, filetype)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.bo[buf].swapfile = false
    vim.bo[buf].filetype = filetype or "markdown"
    vim.api.nvim_buf_set_name(buf, title)
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(content, "\n", { plain = true }))
    vim.cmd("botright split")
    vim.api.nvim_win_set_buf(0, buf)
    return buf
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliDeployTargets", function()
        rpc.request("poor-cli/deployTargets", {}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] deploy targets: " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local lines = { "# Deploy Targets", "" }
            for _, t in ipairs((result or {}).targets or {}) do
                local status = t.available and "✓" or "✗"
                local cfg = t.configFile ~= "" and (" (" .. t.configFile .. ")") or ""
                table.insert(lines, string.format("  [%s] %s: %s%s", status, t.name, t.description or "", cfg))
            end
            if #lines == 2 then table.insert(lines, "  (no targets)") end
            open_scratch("[poor-cli deploy targets]", table.concat(lines, "\n"))
        end) end)
    end, { desc = "List deploy targets" })

    create_command("PoorCliDeployValidate", function()
        rpc.request("poor-cli/deployValidate", {}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] deploy validate: " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = { "# Pre-Deploy Validation", "", r.valid and "Status: PASS" or "Status: FAIL", "" }
            for _, issue in ipairs(r.issues or {}) do
                table.insert(lines, "  - " .. issue)
            end
            if r.targets then
                table.insert(lines, "")
                table.insert(lines, "Configured targets: " .. table.concat(r.targets, ", "))
            end
            open_scratch("[poor-cli deploy validate]", table.concat(lines, "\n"))
        end) end)
    end, { desc = "Validate deploy configuration" })

    create_command("PoorCliDeployHistory", function(opts)
        local limit = tonumber(opts.args) or 20
        rpc.request("poor-cli/deployHistory", { limit = limit }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] deploy history: " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local lines = { "# Deploy History", "" }
            for _, e in ipairs((result or {}).history or {}) do
                local status = e.success and "OK" or "FAIL"
                table.insert(lines, string.format("  [%s] %s %s %s", e.target or "?", status, e.url or "", e.message or ""))
            end
            if #lines == 2 then table.insert(lines, "  (no deployments)") end
            open_scratch("[poor-cli deploy history]", table.concat(lines, "\n"))
        end) end)
    end, { nargs = "?", desc = "Show deploy history (optional limit)" })
end

return M
