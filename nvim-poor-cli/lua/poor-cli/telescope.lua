-- poor-cli/telescope.lua
-- Picker integration for checkpoint browsing/restoration.

local M = {}

local function build_preview_lines(checkpoint)
    local id = checkpoint.checkpointId or "unknown"
    local created_at = checkpoint.createdAt or "-"
    local description = checkpoint.description or ""
    local operation = checkpoint.operationType or "-"
    local file_count = checkpoint.fileCount or 0
    local total_size = checkpoint.totalSizeBytes or 0

    local lines = {
        "Checkpoint: " .. id,
        "Created: " .. created_at,
        "Operation: " .. operation,
        "Files: " .. tostring(file_count),
        "Size (bytes): " .. tostring(total_size),
        "",
        "Description:",
        description ~= "" and description or "(none)",
    }

    local tags = checkpoint.tags
    if type(tags) == "table" and #tags > 0 then
        table.insert(lines, "")
        table.insert(lines, "Tags: " .. table.concat(tags, ", "))
    end

    local affected = checkpoint.files or checkpoint.filePaths or checkpoint.affectedFiles
    table.insert(lines, "")
    table.insert(lines, "Affected files:")
    if type(affected) == "table" and #affected > 0 then
        for _, file_path in ipairs(affected) do
            table.insert(lines, "- " .. tostring(file_path))
        end
    else
        table.insert(lines, "(server response does not include file list)")
    end

    return lines
end

function M.open_checkpoints_picker()
    local pickers = require("poor-cli.pickers")
    local rpc = require("poor-cli.rpc")

    if not rpc.is_running() then
        require("poor-cli.notify").notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    rpc.request("poor-cli/listCheckpoints", { limit = 200 }, function(result, err)
        vim.schedule(function()
            if err then
                require("poor-cli.notify").notify("[poor-cli] Failed to list checkpoints: " .. rpc.format_error(err), vim.log.levels.ERROR)
                return
            end

            if type(result) ~= "table" or result.available == false then
                require("poor-cli.notify").notify("[poor-cli] Checkpoint system is not available", vim.log.levels.WARN)
                return
            end

            local checkpoints = result.checkpoints or {}
            if type(checkpoints) ~= "table" or #checkpoints == 0 then
                require("poor-cli.notify").notify("[poor-cli] No checkpoints available", vim.log.levels.INFO)
                return
            end

            local items = {}
            for _, checkpoint in ipairs(checkpoints) do
                local id = checkpoint.checkpointId or "unknown"
                local created_at = checkpoint.createdAt or "-"
                local file_count = checkpoint.fileCount or 0
                local description = checkpoint.description or ""
                items[#items + 1] = {
                    id = id,
                    label = string.format("%s  %s  %s files  %s", id, created_at, tostring(file_count), description),
                    preview = build_preview_lines(checkpoint),
                    data = checkpoint,
                }
            end
            pickers.pick(items, { title = "poor-cli checkpoints", on_pick = function(checkpoint)
                local checkpoint_id = checkpoint.checkpointId
                if not checkpoint_id or checkpoint_id == "" then
                    require("poor-cli.notify").notify("[poor-cli] Invalid checkpoint selection", vim.log.levels.ERROR)
                    return
                end
                local choice = vim.fn.confirm("Restore checkpoint " .. checkpoint_id .. "?", "&Yes\n&No", 2)
                if choice ~= 1 then return end
                rpc.request("poor-cli/restoreCheckpoint", { checkpointId = checkpoint_id }, function(restore_result, restore_err)
                    vim.schedule(function()
                        if restore_err then
                            require("poor-cli.notify").notify("[poor-cli] Restore failed: " .. vim.inspect(restore_err), vim.log.levels.ERROR)
                        else
                            local restored = restore_result and restore_result.restoredCount or "?"
                            require("poor-cli.notify").notify("[poor-cli] Restored checkpoint " .. checkpoint_id .. " (" .. tostring(restored) .. " files)", vim.log.levels.INFO)
                        end
                    end)
                end)
            end })
        end)
    end)
end

function M.command_palette()
    local pickers = require("poor-cli.pickers")
    local cmds = vim.api.nvim_get_commands({})
    local entries = {}
    for name, info in pairs(cmds) do
        if name:match("^PoorCLI") then
            table.insert(entries, { name = name, desc = info.definition or info.desc or "" })
        end
    end
    table.sort(entries, function(a, b) return a.name < b.name end)
    local items = {}
    for _, entry in ipairs(entries) do
        local display = entry.name
        if entry.desc ~= "" then display = display .. "  " .. entry.desc end
        items[#items + 1] = { id = entry.name, label = display, data = entry.name }
    end
    pickers.pick(items, { title = "poor-cli commands", preview = false, on_pick = function(name) vim.cmd(name) end })
end

return M
