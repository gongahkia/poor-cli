-- poor-cli/search.lua
-- Picker for codebase search results.

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
    local pickers = require("poor-cli.pickers")
    local rpc = require("poor-cli.rpc")

    local search_fn = mode == "semantic" and rpc.semantic_search
        or mode == "vector" and rpc.vector_search
        or rpc.hybrid_search

    search_fn(query, 30, function(result, err)
        vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] search: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local results = (result or {}).results or result or {}
            if #results == 0 then require("poor-cli.notify").notify("[poor-cli] no results for: " .. query, vim.log.levels.INFO); return end
            local items = {}
            for _, entry in ipairs(results) do
                local path = entry.path or entry.file or "?"
                local score = entry.score and string.format(" (%.2f)", entry.score) or ""
                items[#items + 1] = { id = path, label = path .. score, preview = entry.snippet or entry.content or "", data = entry }
            end
            pickers.pick(items, { title = "Search: " .. query, on_pick = function(entry)
                local path = entry.path or entry.file
                if path then
                    vim.cmd("edit " .. vim.fn.fnameescape(path))
                    if entry.line then pcall(vim.api.nvim_win_set_cursor, 0, { entry.line, 0 }) end
                end
            end })
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
            if err then require("poor-cli.notify").notify("[poor-cli] search: " .. rpc.format_error(err), vim.log.levels.ERROR); return end
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
