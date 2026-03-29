local rpc = require("poor-cli.rpc")
local M = {}

function M.create(params, callback) return rpc.request("poor-cli/createCheckpoint", params or {}, callback) end
function M.preview(params, callback) return rpc.request("poor-cli/previewCheckpoint", params or {}, callback) end
function M.gc(params, callback) return rpc.request("poor-cli/gcCheckpoints", params or {}, callback) end

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
    create_command("PoorCliCheckpointCreate", function()
        vim.ui.input({ prompt = "Checkpoint label: " }, function(label)
            if not label or label == "" then return end
            M.create({ label = label }, function(result, err) vim.schedule(function()
                if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
                else vim.notify("[poor-cli] checkpoint created: " .. tostring((result or {}).checkpointId or ""), vim.log.levels.INFO) end
            end) end)
        end)
    end, { desc = "Create checkpoint" })
    create_command("PoorCliCheckpointPreview", function(opts)
        M.preview({ checkpointId = opts.args }, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# checkpoint preview: " .. opts.args, "",
                "Files: " .. tostring(r.fileCount or 0),
                "Size: " .. tostring(r.totalSizeBytes or 0) .. " bytes",
                "Created: " .. tostring(r.createdAt or "-"),
                "Description: " .. tostring(r.description or ""),
                "",
            }
            local files = r.files or r.filePaths or {}
            if #files > 0 then
                table.insert(lines, "Affected files:")
                for _, f in ipairs(files) do table.insert(lines, "- " .. tostring(f)) end
            end
            open_scratch("[poor-cli checkpoint preview]", table.concat(lines, "\n"), "markdown")
        end) end)
    end, { nargs = 1, desc = "Preview checkpoint" })
    create_command("PoorCliCheckpointGc", function()
        M.gc({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else vim.notify("[poor-cli] gc complete: " .. tostring((result or {}).removedCount or 0) .. " removed", vim.log.levels.INFO) end
        end) end)
    end, { desc = "Garbage collect checkpoints" })
end

return M
