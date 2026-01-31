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
    return rpc.is_running()
end

source.get_debug_name = function()
    return "poor-cli"
end

source.complete = function(self, params, callback)
    local rpc = require("poor-cli.rpc")
    
    if not rpc.is_running() then
        callback({ items = {}, isIncomplete = false })
        return
    end
    
    local bufnr = vim.api.nvim_get_current_buf()
    local cursor = params.context.cursor
    local line = cursor.line
    local col = cursor.col
    
    -- Get buffer content
    local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
    
    -- Build code before/after cursor
    local code_before = table.concat(vim.list_slice(lines, 1, line), "\n")
    if line <= #lines then
        local current_line = lines[line + 1] or ""
        code_before = code_before .. "\n" .. current_line:sub(1, col)
    end
    
    local code_after = ""
    if line + 1 <= #lines then
        local current_line = lines[line + 1] or ""
        code_after = current_line:sub(col + 1)
    end
    if line + 2 <= #lines then
        code_after = code_after .. "\n" .. table.concat(vim.list_slice(lines, line + 2), "\n")
    end
    
    local file_path = vim.fn.expand("%:p")
    local language = vim.bo[bufnr].filetype
    
    -- Request completion from server
    rpc.request("poor-cli/inlineComplete", {
        codeBefore = code_before,
        codeAfter = code_after,
        instruction = "",
        filePath = file_path,
        language = language,
    }, function(result, err)
        if err or not result or not result.completion then
            callback({ items = {}, isIncomplete = false })
            return
        end
        
        local completion_text = result.completion
        
        -- Create completion item
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
        
        -- Handle multi-line completions
        if completion_text:find("\n") then
            item.insertTextFormat = 2  -- Snippet format
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
        vim.notify("[poor-cli] nvim-cmp not found, skipping cmp source", vim.log.levels.DEBUG)
        return
    end
    
    cmp.register_source("poor-cli", source.new())
    
    -- Optionally add to cmp sources
    local config = cmp.get_config()
    local sources = config.sources or {}
    
    -- Check if already added
    for _, s in ipairs(sources) do
        if s.name == "poor-cli" then
            return  -- Already registered
        end
    end
    
    -- Add poor-cli source with lower priority
    table.insert(sources, {
        name = "poor-cli",
        priority = 50,  -- Lower than LSP
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
