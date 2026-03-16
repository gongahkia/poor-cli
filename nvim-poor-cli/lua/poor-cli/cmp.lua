-- poor-cli/cmp.lua
-- nvim-cmp source for poor-cli AI completions

local source = {}

source.new = function()
    return setmetatable({}, { __index = source })
end

source.get_keyword_pattern = function()
    return [[\k\+]]
end

source.get_trigger_characters = function()
    return { ".", ":", "(", " " }
end

source.is_available = function()
    local rpc = require("poor-cli.rpc")
    local inline = require("poor-cli.inline")
    local enabled = inline.is_enabled_for_buffer(vim.api.nvim_get_current_buf(), { manual = false })
    return rpc.is_running() and enabled
end

source.get_debug_name = function()
    return "poor-cli"
end

source.complete = function(self, params, callback)
    local inline = require("poor-cli.inline")
    local rpc = require("poor-cli.rpc")

    if not rpc.is_running() then
        callback({ items = {}, isIncomplete = false })
        return
    end

    local bufnr = vim.api.nvim_get_current_buf()
    local enabled = inline.is_enabled_for_buffer(bufnr, { manual = false })
    if not enabled then
        callback({ items = {}, isIncomplete = false })
        return
    end

    local cursor = params.context.cursor
    local line = cursor.line + 1
    local col = cursor.col

    local payload = inline.build_completion_request({
        bufnr = bufnr,
        line = line,
        col = col,
        instruction = "",
        request_id = string.format("cmp-%d-%d", os.time(), col),
    })
    local language = payload.language

    rpc.request("poor-cli/inlineComplete", payload, function(result, err)
        if err or not result or not result.completion then
            callback({ items = {}, isIncomplete = false })
            return
        end

        local completion_text = result.completion
        local item = {
            label = completion_text:match("^([^\n]*)") or completion_text,
            insertText = completion_text,
            kind = vim.lsp.protocol.CompletionItemKind.Snippet,
            detail = "[poor-cli]",
            documentation = {
                kind = "markdown",
                value = "```" .. language .. "\n" .. completion_text .. "\n```",
            },
        }
        if completion_text:find("\n") then
            item.insertTextFormat = 2
        end

        callback({
            items = { item },
            isIncomplete = false,
        })
    end)
end

-- Register the source with nvim-cmp
local M = {}

function M.setup()
    local has_cmp, cmp = pcall(require, "cmp")
    if not has_cmp then
        return
    end

    cmp.register_source("poor-cli", source.new())

    local current = cmp.get_config()
    local sources = current.sources or {}
    for _, s in ipairs(sources) do
        if s.name == "poor-cli" then
            return
        end
    end

    table.insert(sources, {
        name = "poor-cli",
        priority = 50,
        group_index = 2,
        keyword_length = 3,
        max_item_count = 3,
    })

    cmp.setup({ sources = sources })
end

-- Manual trigger function
function M.trigger()
    local has_cmp, cmp = pcall(require, "cmp")
    if not has_cmp then
        return
    end
    
    cmp.complete({
        config = {
            sources = {
                { name = "poor-cli" }
            }
        }
    })
end

return M
