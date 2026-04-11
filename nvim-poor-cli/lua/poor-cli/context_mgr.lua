local rpc = require("poor-cli.rpc")
local M = {}

function M.preview(params, callback) return rpc.request("poor-cli/previewContext", params or {}, callback) end
function M.compact(params, callback) return rpc.request("poor-cli/compactContext", params or {}, callback) end
function M.preview_mutation(params, callback) return rpc.request("poor-cli/previewMutation", params or {}, callback) end

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

local function open_float(title, lines)
    local buf = vim.api.nvim_create_buf(false, true)
    vim.bo[buf].buftype = "nofile"
    vim.bo[buf].bufhidden = "wipe"
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
    local width = math.min(80, vim.o.columns - 4)
    local height = math.min(#lines + 2, vim.o.lines - 4)
    local row = math.floor((vim.o.lines - height) / 2)
    local col = math.floor((vim.o.columns - width) / 2)
    vim.api.nvim_open_win(buf, true, {
        relative = "editor", width = width, height = height, row = row, col = col,
        style = "minimal", border = "rounded", title = title,
    })
    return buf
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCliContextPreview", function()
        M.preview({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# context preview", "",
                "Total tokens: " .. tostring(r.totalTokens or 0),
                "Budget tokens: " .. tostring(r.budgetTokens or 0),
                "Truncated: " .. tostring(r.truncated == true),
                "",
            }
            for _, item in ipairs(r.selected or {}) do
                if type(item) == "table" then
                    table.insert(lines, "- " .. tostring(item.path or "") .. " [" .. tostring(item.source or "auto") .. "]")
                end
            end
            if type(r.excluded) == "table" and #r.excluded > 0 then
                table.insert(lines, "")
                table.insert(lines, "Excluded:")
                for _, item in ipairs(r.excluded) do
                    if type(item) == "table" then
                        table.insert(lines, "- " .. tostring(item.path or "") .. " [" .. tostring(item.excludedReason or "") .. "]")
                    end
                end
            end
            open_float("context preview", lines)
        end) end)
    end, { desc = "Preview context" })
    create_command("PoorCliContextCompact", function()
        M.compact({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR)
            else
                local r = result or {}
                vim.notify("[poor-cli] compacted: " .. tostring(r.removedTokens or 0) .. " tokens freed", vim.log.levels.INFO)
            end
        end) end)
    end, { desc = "Compact context" })
    create_command("PoorCliMutationPreview", function()
        M.preview_mutation({}, function(result, err) vim.schedule(function()
            if err then vim.notify("[poor-cli] " .. vim.inspect(err), vim.log.levels.ERROR); return end
            local r = result or {}
            local lines = {
                "# mutation preview", "",
                "Intent: " .. tostring(r.intent or ""),
                "Files affected: " .. tostring(r.fileCount or 0),
                "Checkpoint: " .. tostring(r.checkpointId or "none"),
                "",
            }
            for _, f in ipairs(r.files or {}) do
                if type(f) == "table" then
                    table.insert(lines, "- " .. tostring(f.path or f) .. " [" .. tostring(f.action or "") .. "]")
                else
                    table.insert(lines, "- " .. tostring(f))
                end
            end
            if r.diff and r.diff ~= "" then
                table.insert(lines, "")
                table.insert(lines, "Diff:")
                table.insert(lines, r.diff)
            end
            open_float("mutation preview", lines)
        end) end)
    end, { desc = "Preview mutation" })
end

return M
