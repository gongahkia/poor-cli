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
    create_command("PoorCliSandboxStatus", function()
        local sandbox = rpc.request_sync("poor-cli/getSandboxStatus", {}, 5000) or {}
        local docker = rpc.request_sync("poor-cli/getDockerSandboxStatus", {}, 5000) or {}
        local lines = { "# Sandbox Status", "" }
        for k, v in pairs(sandbox) do
            table.insert(lines, string.format("  %s: %s", k, tostring(v)))
        end
        table.insert(lines, "")
        table.insert(lines, "# Docker Sandbox")
        table.insert(lines, "")
        for k, v in pairs(docker) do
            table.insert(lines, string.format("  %s: %s", k, tostring(v)))
        end
        open_scratch("[poor-cli sandbox status]", table.concat(lines, "\n"))
    end, { desc = "Show sandbox and Docker sandbox status" })
end

return M
