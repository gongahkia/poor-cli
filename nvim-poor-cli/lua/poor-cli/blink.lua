-- poor-cli/blink.lua
-- blink.cmp source for poor-cli AI completions

local inline = require("poor-cli.inline")
local rpc = require("poor-cli.rpc")

local source = {}
source.__index = source

local function empty_result()
    return {
        items = {},
        is_incomplete_backward = false,
        is_incomplete_forward = false,
    }
end

local function first_line(text)
    return (text or ""):match("^([^\n]*)") or (text or "")
end

local function build_completion_item(completion_text, language, line, col)
    return {
        label = first_line(completion_text),
        kind = vim.lsp.protocol.CompletionItemKind.Snippet,
        detail = "[poor-cli]",
        documentation = {
            kind = "markdown",
            value = "```" .. (language or "") .. "\n" .. completion_text .. "\n```",
        },
        insertTextFormat = vim.lsp.protocol.InsertTextFormat.PlainText,
        textEdit = {
            newText = completion_text,
            range = {
                start = {
                    line = line,
                    character = col,
                },
                ["end"] = {
                    line = line,
                    character = col,
                },
            },
        },
    }
end

function source.new(opts)
    return setmetatable({
        opts = opts or {},
    }, source)
end

function source:enabled()
    if not rpc.is_running() then
        return false
    end
    local enabled = inline.is_enabled_for_buffer(vim.api.nvim_get_current_buf(), { manual = false })
    return enabled
end

function source:get_trigger_characters()
    return self.opts.trigger_characters or { ".", ":", "(", " " }
end

function source:get_completions(_ctx, callback)
    if not rpc.is_running() then
        callback(empty_result())
        return function() end
    end

    local bufnr = vim.api.nvim_get_current_buf()
    local enabled = inline.is_enabled_for_buffer(bufnr, { manual = false })
    if not enabled then
        callback(empty_result())
        return function() end
    end

    local cursor = vim.api.nvim_win_get_cursor(0)
    local line = cursor[1]
    local col = cursor[2]
    local request_id = string.format("blink-%d-%d", os.time(), col)
    local payload = inline.build_completion_request({
        bufnr = bufnr,
        line = line,
        col = col,
        instruction = "",
        request_id = request_id,
    })
    payload.streamPartial = false

    local cancelled = false
    local rpc_request_id = rpc.request("poor-cli/inlineComplete", payload, function(result, err)
        if cancelled then
            return
        end

        if err or not result or not result.completion or result.completion == "" then
            callback(empty_result())
            return
        end

        callback({
            items = {
                build_completion_item(result.completion, payload.language, line - 1, col),
            },
            is_incomplete_backward = false,
            is_incomplete_forward = false,
        })
    end)

    return function()
        cancelled = true
        if rpc_request_id then
            rpc.cancel_request(rpc_request_id, {
                code = -32800,
                message = "Request cancelled",
                data = {
                    request_id = request_id,
                },
            })
        end
    end
end

local M = {}

function M.new(opts)
    return source.new(opts)
end

function M.provider(overrides)
    return vim.tbl_deep_extend("force", {
        name = "poor-cli",
        module = "poor-cli.blink",
        async = true,
        opts = {},
        score_offset = 100,
        max_items = 1,
    }, overrides or {})
end

return M
