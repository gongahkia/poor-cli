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
    vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
    return buf
end

local function notify(msg, level) require("poor-cli.notify").notify("[poor-cli] " .. msg, level) end

function M.setup()
    local spec = require("poor-cli.command_spec")
    local diag_spec = {
        verb_names = { "recovery", "sandbox-status" },
        verbs = {
            recovery = function(fargs)
                local error_text = table.concat(fargs, " ")
                if error_text == "" then error_text = vim.fn.getreg("+") or "" end
                rpc.request("poor-cli/getRecoverySuggestions", { error = error_text }, function(result, err) vim.schedule(function()
                    if err then notify(rpc.format_error(err), vim.log.levels.ERROR); return end
                    local suggestions = (result or {}).suggestions or {}
                    local lines = { "# Recovery Suggestions", "" }
                    if #suggestions == 0 then
                        table.insert(lines, "no suggestions for this error")
                        open_scratch("[poor-cli recovery]", table.concat(lines, "\n"))
                        return
                    end
                    for _, s in ipairs(suggestions) do
                        table.insert(lines, string.format("## %s (priority: %s)", s.title or "?", tostring(s.priority or "")))
                        table.insert(lines, tostring(s.description or ""))
                        if type(s.commands) == "table" and #s.commands > 0 then
                            table.insert(lines, ""); table.insert(lines, "Commands:")
                            for _, cmd in ipairs(s.commands) do table.insert(lines, "  " .. cmd) end
                        end
                        table.insert(lines, "")
                    end
                    open_scratch("[poor-cli recovery]", table.concat(lines, "\n"))
                end) end)
            end,
            ["sandbox-status"] = function()
                local sandbox = rpc.request_sync("poor-cli/getSandboxStatus", {}, 5000) or {}
                local docker = rpc.request_sync("poor-cli/getDockerSandboxStatus", {}, 5000) or {}
                local lines = { "# Sandbox Status", "" }
                for k, v in pairs(sandbox) do table.insert(lines, string.format("  %s: %s", k, tostring(v))) end
                table.insert(lines, "")
                table.insert(lines, "# Docker Sandbox")
                table.insert(lines, "")
                for k, v in pairs(docker) do table.insert(lines, string.format("  %s: %s", k, tostring(v))) end
                open_scratch("[poor-cli sandbox status]", table.concat(lines, "\n"))
            end,
        },
    }
    if spec.get("diag") then
        spec.extend("diag", diag_spec)
    else
        spec.install("diag", vim.tbl_deep_extend("force", {
            desc = "Diagnostics, recovery, health checks",
            verb_names = {},
            verbs = {},
        }, diag_spec))
    end
end

return M
