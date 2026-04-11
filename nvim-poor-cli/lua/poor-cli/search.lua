-- poor-cli/search.lua
-- Telescope picker for codebase search results.

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

function M.pick(query, mode)
    local ok, telescope = pcall(require, "telescope.pickers")
    if not ok then
        M.fallback(query, mode)
        return
    end
    local finders = require("telescope.finders")
    local conf = require("telescope.config").values
    local actions = require("telescope.actions")
    local action_state = require("telescope.actions.state")
    local previewers = require("telescope.previewers")
    local rpc = require("poor-cli.rpc")

    local search_fn = mode == "semantic" and rpc.semantic_search
        or mode == "vector" and rpc.vector_search
        or rpc.hybrid_search

    search_fn(query, 30, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] search: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local results = (result or {}).results or result or {}
            if #results == 0 then vim.notify("[poor-cli] no results for: " .. query, vim.log.levels.INFO); return end
            telescope.new({}, {
                prompt_title = "Search: " .. query,
                finder = finders.new_table({
                    results = results,
                    entry_maker = function(entry)
                        local path = entry.path or entry.file or "?"
                        local score = entry.score and string.format(" (%.2f)", entry.score) or ""
                        return {
                            value = entry,
                            display = path .. score,
                            ordinal = path,
                            filename = path,
                            lnum = entry.line or 1,
                        }
                    end,
                }),
                sorter = conf.generic_sorter({}),
                previewer = previewers.new_buffer_previewer({
                    define_preview = function(self, entry)
                        local snippet = entry.value.snippet or entry.value.content or ""
                        vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, vim.split(snippet, "\n", { plain = true }))
                    end,
                }),
                attach_mappings = function(prompt_bufnr)
                    actions.select_default:replace(function()
                        local entry = action_state.get_selected_entry()
                        actions.close(prompt_bufnr)
                        if entry and entry.filename then
                            vim.cmd("edit " .. vim.fn.fnameescape(entry.filename))
                            if entry.lnum then pcall(vim.api.nvim_win_set_cursor, 0, { entry.lnum, 0 }) end
                        end
                    end)
                    return true
                end,
            }):find()
        end)
    end)
end

function M.fallback(query, mode)
    local rpc = require("poor-cli.rpc")
    local search_fn = mode == "semantic" and rpc.semantic_search
        or mode == "vector" and rpc.vector_search
        or rpc.hybrid_search
    search_fn(query, 20, function(result, err)
        vim.schedule(function()
            if err then vim.notify("[poor-cli] search: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local results = (result or {}).results or result or {}
            local lines = { "# search: " .. query .. " (" .. (mode or "hybrid") .. ")", "" }
            for i, r in ipairs(results) do
                local path = r.path or r.file or "?"
                local score = r.score and string.format(" (%.2f)", r.score) or ""
                table.insert(lines, string.format("%d. `%s`%s", i, path, score))
                if r.snippet or r.content then table.insert(lines, "   " .. (r.snippet or r.content):sub(1, 120)) end
            end
            if #results == 0 then table.insert(lines, "no results") end
            open_scratch("[poor-cli search]", table.concat(lines, "\n"))
        end)
    end)
end

return M
