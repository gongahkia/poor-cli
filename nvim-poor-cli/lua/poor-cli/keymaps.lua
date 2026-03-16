-- poor-cli/keymaps.lua
-- Default keymaps for poor-cli

local M = {}

local function safe_map(mode, lhs, rhs, opts)
    if lhs == nil or lhs == "" then
        return
    end
    pcall(vim.keymap.del, mode, lhs, { buffer = opts and opts.buffer or nil })
    vim.keymap.set(mode, lhs, rhs, opts or {})
end

function M.setup()
    local config = require("poor-cli.config")
    local inline = require("poor-cli.inline")
    local chat = require("poor-cli.chat")
    local telescope = require("poor-cli.telescope")
    
    -- Trigger completion in insert mode
    safe_map("i", config.get("trigger_key"), function()
        inline.trigger({ manual = true })
    end, { desc = "Trigger poor-cli completion" })
    
    -- Accept completion line - only if ghost text is visible, otherwise fallback
    safe_map("i", config.get("accept_key"), function()
        if inline.has_completion() then
            inline.accept_line()
        else
            return vim.api.nvim_replace_termcodes("<Tab>", true, false, true)
        end
    end, { expr = true, desc = "Accept poor-cli completion line or Tab" })

    -- Accept next word of ghost text
    safe_map("i", config.get("accept_word_key"), function()
        if inline.has_completion() then
            inline.accept_word()
            return ""
        else
            return vim.api.nvim_replace_termcodes("<C-Right>", true, false, true)
        end
    end, { expr = true, desc = "Accept poor-cli completion word or Ctrl+Right" })

    -- Dismiss completion
    safe_map("i", config.get("dismiss_key"), function()
        if inline.has_completion() then
            inline.dismiss()
            return ""
        else
            return vim.api.nvim_replace_termcodes("<Esc>", true, false, true)
        end
    end, { expr = true, desc = "Dismiss poor-cli completion or Escape" })
    
    -- Toggle chat in normal mode
    safe_map("n", config.get("chat_key"), function()
        chat.toggle()
    end, { desc = "Toggle poor-cli chat" })

    local checkpoints_key = config.get("checkpoints_key")
    if checkpoints_key and checkpoints_key ~= "" then
        safe_map("n", checkpoints_key, function()
            telescope.open_checkpoints_picker()
        end, { desc = "Browse poor-cli checkpoints" })
    end
    
    -- Send selection to chat in visual mode
    safe_map("v", config.get("chat_key"), function()
        chat.send_with_selection()
    end, { desc = "Send selection to poor-cli chat" })
    
    -- Additional useful keymaps (not configurable, but standard)
    
    -- Alt+Enter to trigger completion with instruction
    safe_map("i", "<M-CR>", function()
        inline.trigger_with_instruction()
    end, { desc = "Trigger poor-cli completion with instruction" })
    
    -- In normal mode: gc for generate completion
    safe_map("n", "gc", function()
        vim.cmd("startinsert")
        vim.defer_fn(function()
            inline.trigger({ manual = true })
        end, 50)
    end, { desc = "Generate completion at cursor" })
    
    -- Visual mode refactor
    safe_map("v", "<leader>pr", function()
        -- Get visual selection bounds
        local start_pos = vim.fn.getpos("'<")
        local end_pos = vim.fn.getpos("'>")
        vim.cmd(start_pos[2] .. "," .. end_pos[2] .. "PoorCliRefactor")
    end, { desc = "Refactor selection with poor-cli" })
    
    -- Quick explain
    safe_map("v", "<leader>pe", function()
        local start_pos = vim.fn.getpos("'<")
        local end_pos = vim.fn.getpos("'>")
        vim.cmd(start_pos[2] .. "," .. end_pos[2] .. "PoorCliExplain")
    end, { desc = "Explain selection with poor-cli" })
end

return M
