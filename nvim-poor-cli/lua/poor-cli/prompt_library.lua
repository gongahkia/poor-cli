local rpc = require("poor-cli.rpc")
local M = {}

function M.save(params, callback) return rpc.request("poor-cli/promptSave", params or {}, callback) end
function M.load(params, callback) return rpc.request("poor-cli/promptLoad", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/promptList", params or {}, callback) end
function M.delete(params, callback) return rpc.request("poor-cli/promptDelete", params or {}, callback) end

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
    create_command("PoorCliPromptList", function()
        M.list({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local prompts = (result or {}).prompts or {}
            local lines = { "# saved prompts", "" }
            for _, name in ipairs(prompts) do table.insert(lines, "  " .. name) end
            if #prompts == 0 then table.insert(lines, "no saved prompts") end
            open_scratch("[poor-cli prompts]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { desc = "List saved prompts" })
    create_command("PoorCliPromptSave", function()
        vim.ui.input({ prompt = "Prompt name: " }, function(name)
            if not name or name == "" then return end
            vim.ui.input({ prompt = "Prompt content: " }, function(content)
                if not content or content == "" then return end
                M.save({ name = name, content = content }, function(_, err) vim.schedule(function()
                    if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
                    else vim.notify("[poor-cli] prompt saved: " .. name, vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Save a prompt" })
    create_command("PoorCliPromptLoad", function(opts)
        M.load({ name = opts.args }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local content = (result or {}).content or ""
            open_scratch("[poor-cli prompt " .. opts.args .. "]", content, "markdown")
        end) end)
    end, { nargs = 1, desc = "Load a saved prompt" })
    create_command("PoorCliPromptDelete", function(opts)
        M.delete({ name = opts.args }, function(_, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] prompt deleted: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Delete a saved prompt" })
end

return M
