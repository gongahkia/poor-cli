-- poor-cli/keymaps.lua
-- Default keymaps for poor-cli

local M = {}

function M.setup()
    local config = require("poor-cli.config")
    local inline = require("poor-cli.inline")
    local chat = require("poor-cli.chat")
    
    -- Trigger completion in insert mode
    vim.keymap.set("i", config.get("trigger_key"), function()
        inline.trigger()
    end, { desc = "Trigger poor-cli completion" })
    
    -- Accept completion - only if ghost text is visible, otherwise fallback
    vim.keymap.set("i", config.get("accept_key"), function()
        if inline.has_completion() then
            inline.accept()
        else
            -- Fallback to normal Tab behavior
            return vim.api.nvim_replace_termcodes("<Tab>", true, false, true)
        end
    end, { expr = true, desc = "Accept poor-cli completion or Tab" })
    
    -- Dismiss completion
    vim.keymap.set("i", config.get("dismiss_key"), function()
        if inline.has_completion() then
            inline.dismiss()
            return ""
        else
            return vim.api.nvim_replace_termcodes("<Esc>", true, false, true)
        end
    end, { expr = true, desc = "Dismiss poor-cli completion or Escape" })
    
    -- Toggle chat in normal mode
    vim.keymap.set("n", config.get("chat_key"), function()
        chat.toggle()
    end, { desc = "Toggle poor-cli chat" })
    
    -- Send selection to chat in visual mode
    vim.keymap.set("v", config.get("chat_key"), function()
        chat.send_with_selection()
    end, { desc = "Send selection to poor-cli chat" })
    
    -- Additional useful keymaps (not configurable, but standard)
    
    -- Alt+Enter to trigger completion with instruction
    vim.keymap.set("i", "<M-CR>", function()
        inline.trigger_with_instruction()
    end, { desc = "Trigger poor-cli completion with instruction" })
    
    -- In normal mode: gc for generate completion
    vim.keymap.set("n", "gc", function()
        vim.cmd("startinsert")
        vim.defer_fn(function()
            inline.trigger()
        end, 50)
    end, { desc = "Generate completion at cursor" })
    
    -- Visual mode refactor
    vim.keymap.set("v", "<leader>pr", function()
        -- Get visual selection bounds
        local start_pos = vim.fn.getpos("'<")
        local end_pos = vim.fn.getpos("'>")
        vim.cmd(start_pos[2] .. "," .. end_pos[2] .. "PoorCliRefactor")
    end, { desc = "Refactor selection with poor-cli" })
    
    -- Quick explain
    vim.keymap.set("v", "<leader>pe", function()
        local start_pos = vim.fn.getpos("'<")
        local end_pos = vim.fn.getpos("'>")
        vim.cmd(start_pos[2] .. "," .. end_pos[2] .. "PoorCliExplain")
    end, { desc = "Explain selection with poor-cli" })
end

return M
