-- poor-cli/telescope.lua
-- Telescope integration for checkpoint browsing/restoration.

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
    local has_telescope, pickers = pcall(require, "telescope.pickers")
    if not has_telescope then
        vim.notify("[poor-cli] telescope.nvim is not installed", vim.log.levels.ERROR)
        return
    end

    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    local rpc = require("poor-cli.rpc")

    if not rpc.is_running() then
        vim.notify("[poor-cli] Server not running", vim.log.levels.WARN)
        return
    end

    rpc.request("poor-cli/listCheckpoints", { limit = 200 }, function(result, err)
        vim.schedule(function()
            if err then
                vim.notify("[poor-cli] Failed to list checkpoints: " .. vim.inspect(err), vim.log.levels.ERROR)
                return
            end

            if type(result) ~= "table" or result.available == false then
                vim.notify("[poor-cli] Checkpoint system is not available", vim.log.levels.WARN)
                return
            end

            local checkpoints = result.checkpoints or {}
            if type(checkpoints) ~= "table" or #checkpoints == 0 then
                vim.notify("[poor-cli] No checkpoints available", vim.log.levels.INFO)
                return
            end

            pickers
                .new({}, {
                    prompt_title = "poor-cli checkpoints",
                    finder = finders.new_table({
                        results = checkpoints,
                        entry_maker = function(checkpoint)
                            local id = checkpoint.checkpointId or "unknown"
                            local created_at = checkpoint.createdAt or "-"
                            local file_count = checkpoint.fileCount or 0
                            local description = checkpoint.description or ""
                            local display = string.format(
                                "%s  %s  %s files  %s",
                                id,
                                created_at,
                                tostring(file_count),
                                description
                            )
                            return {
                                value = checkpoint,
                                ordinal = id .. " " .. created_at .. " " .. description,
                                display = display,
                            }
                        end,
                    }),
                    sorter = conf.generic_sorter({}),
                    previewer = previewers.new_buffer_previewer({
                        title = "Checkpoint Preview",
                        define_preview = function(self, entry)
                            local lines = build_preview_lines(entry.value)
                            vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, lines)
                        end,
                    }),
                    attach_mappings = function(prompt_bufnr)
                        actions.select_default:replace(function()
                            actions.close(prompt_bufnr)
                            local selected = action_state.get_selected_entry()
                            if not selected then
                                return
                            end

                            local checkpoint = selected.value or {}
                            local checkpoint_id = checkpoint.checkpointId
                            if not checkpoint_id or checkpoint_id == "" then
                                vim.notify("[poor-cli] Invalid checkpoint selection", vim.log.levels.ERROR)
                                return
                            end

                            local choice = vim.fn.confirm(
                                "Restore checkpoint " .. checkpoint_id .. "?",
                                "&Yes\n&No",
                                2
                            )
                            if choice ~= 1 then
                                return
                            end

                            rpc.request("poor-cli/restoreCheckpoint", {
                                checkpointId = checkpoint_id,
                            }, function(restore_result, restore_err)
                                vim.schedule(function()
                                    if restore_err then
                                        vim.notify(
                                            "[poor-cli] Restore failed: " .. vim.inspect(restore_err),
                                            vim.log.levels.ERROR
                                        )
                                    else
                                        local restored = restore_result and restore_result.restoredCount or "?"
                                        vim.notify(
                                            "[poor-cli] Restored checkpoint "
                                                .. checkpoint_id
                                                .. " ("
                                                .. tostring(restored)
                                                .. " files)",
                                            vim.log.levels.INFO
                                        )
                                    end
                                end)
                            end)
                        end)
                        return true
                    end,
                })
                :find()
        end)
    end)
end

return M
