-- poor-cli/commands.lua
-- Vim commands for poor-cli

local M = {}

function M.setup()
    local rpc = require("poor-cli.rpc")
    local chat = require("poor-cli.chat")
    local inline = require("poor-cli.inline")
    
    -- Server control
    vim.api.nvim_create_user_command("PoorCliStart", function()
        rpc.start()
        -- Initialize after start
        vim.defer_fn(function()
            local config = require("poor-cli.config")
            rpc.request("initialize", {
                provider = config.get("provider"),
                model = config.get("model"),
            }, function(result, err)
                if err then
                    vim.notify("[poor-cli] Init failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                else
                    vim.notify("[poor-cli] Initialized", vim.log.levels.INFO)
                end
            end)
        end, 500)
    end, { desc = "Start poor-cli server" })
    
    vim.api.nvim_create_user_command("PoorCliStop", function()
        rpc.stop()
    end, { desc = "Stop poor-cli server" })
    
    -- Chat commands
    vim.api.nvim_create_user_command("PoorCliChat", function()
        chat.toggle()
    end, { desc = "Toggle poor-cli chat panel" })
    
    vim.api.nvim_create_user_command("PoorCliSend", function(opts)
        if opts.args and opts.args ~= "" then
            chat.send(opts.args)
        else
            chat.prompt_and_send()
        end
    end, { nargs = "*", desc = "Send message to poor-cli" })
    
    vim.api.nvim_create_user_command("PoorCliClear", function()
        chat.clear()
    end, { desc = "Clear chat history" })
    
    -- Completion commands
    vim.api.nvim_create_user_command("PoorCliComplete", function()
        inline.trigger()
    end, { desc = "Trigger inline completion" })
    
    vim.api.nvim_create_user_command("PoorCliAccept", function()
        inline.accept()
    end, { desc = "Accept inline completion" })
    
    vim.api.nvim_create_user_command("PoorCliDismiss", function()
        inline.dismiss()
    end, { desc = "Dismiss inline completion" })
    
    -- Provider commands
    vim.api.nvim_create_user_command("PoorCliSwitchProvider", function(opts)
        local args = vim.split(opts.args, " ")
        local provider = args[1]
        local model = args[2]
        
        if not provider or provider == "" then
            vim.ui.select({ "gemini", "openai", "anthropic", "ollama" }, {
                prompt = "Select provider:",
            }, function(choice)
                if choice then
                    rpc.request("poor-cli/switchProvider", {
                        provider = choice,
                    }, function(result, err)
                        if err then
                            vim.notify("[poor-cli] Switch failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                        else
                            vim.notify("[poor-cli] Switched to " .. choice, vim.log.levels.INFO)
                        end
                    end)
                end
            end)
            return
        end
        
        rpc.request("poor-cli/switchProvider", {
            provider = provider,
            model = model,
        }, function(result, err)
            vim.schedule(function()
                if err then
                    vim.notify("[poor-cli] Switch failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                else
                    vim.notify("[poor-cli] Switched to " .. provider, vim.log.levels.INFO)
                end
            end)
        end)
    end, { nargs = "*", desc = "Switch AI provider" })
    
    -- Status command
    vim.api.nvim_create_user_command("PoorCliStatus", function()
        if not rpc.is_running() then
            vim.notify("[poor-cli] Server not running", vim.log.levels.INFO)
            return
        end
        
        rpc.request("poor-cli/getProviderInfo", {}, function(result, err)
            vim.schedule(function()
                if err then
                    vim.notify("[poor-cli] Status error: " .. vim.inspect(err), vim.log.levels.ERROR)
                else
                    local info = "Provider: " .. (result.name or "unknown") .. 
                                 "\nModel: " .. (result.model or "unknown")
                    vim.notify("[poor-cli] " .. info, vim.log.levels.INFO)
                end
            end)
        end)
    end, { desc = "Show poor-cli status" })
    
    -- AI-powered commands
    vim.api.nvim_create_user_command("PoorCliExplain", function(opts)
        M.explain_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Explain selected code" })
    
    vim.api.nvim_create_user_command("PoorCliRefactor", function(opts)
        M.refactor_code(opts.range, opts.line1, opts.line2)
    end, { range = true, desc = "Refactor selected code" })
    
    vim.api.nvim_create_user_command("PoorCliTest", function()
        M.generate_tests()
    end, { desc = "Generate tests for current function" })
    
    vim.api.nvim_create_user_command("PoorCliDoc", function()
        M.generate_docs()
    end, { desc = "Generate documentation for current function" })
end

-- Explain code (line range or current line)
function M.explain_code(range, line1, line2)
    local rpc = require("poor-cli.rpc")
    local chat = require("poor-cli.chat")
    
    local lines
    if range > 0 then
        lines = vim.api.nvim_buf_get_lines(0, line1 - 1, line2, false)
    else
        lines = { vim.api.nvim_get_current_line() }
    end
    
    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype
    
    chat.open()
    
    rpc.request("poor-cli/chat", {
        message = "Please explain this " .. language .. " code:\n\n```" .. language .. "\n" .. code .. "\n```"
    }, function(result, err)
        vim.schedule(function()
            if err then
                chat.append_message("assistant", "Error: " .. vim.inspect(err))
            elseif result and result.content then
                chat.append_message("user", "Explain:\n```" .. language .. "\n" .. code .. "\n```")
                chat.append_message("assistant", result.content)
            end
        end)
    end)
end

-- Refactor code
function M.refactor_code(range, line1, line2)
    local rpc = require("poor-cli.rpc")
    
    local lines
    if range > 0 then
        lines = vim.api.nvim_buf_get_lines(0, line1 - 1, line2, false)
    else
        vim.notify("[poor-cli] Select code to refactor", vim.log.levels.WARN)
        return
    end
    
    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype
    
    vim.ui.input({ prompt = "Refactor instruction: " }, function(instruction)
        if not instruction or instruction == "" then
            return
        end
        
        vim.notify("[poor-cli] Refactoring...", vim.log.levels.INFO)
        
        rpc.request("poor-cli/chat", {
            message = "Refactor this " .. language .. " code. Return ONLY the refactored code, no explanations.\n\n" ..
                      "Instruction: " .. instruction .. "\n\n" ..
                      "```" .. language .. "\n" .. code .. "\n```"
        }, function(result, err)
            vim.schedule(function()
                if err then
                    vim.notify("[poor-cli] Refactor failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                    return
                end
                
                if result and result.content then
                    -- Clean up code block markers if present
                    local new_code = result.content
                    new_code = new_code:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                    
                    local new_lines = vim.split(new_code, "\n", { plain = true })
                    vim.api.nvim_buf_set_lines(0, line1 - 1, line2, false, new_lines)
                    
                    vim.notify("[poor-cli] Refactored!", vim.log.levels.INFO)
                end
            end)
        end)
    end)
end

-- Generate tests for current function
function M.generate_tests()
    local rpc = require("poor-cli.rpc")
    
    -- Try to get current function using treesitter
    local node = vim.treesitter.get_node()
    local func_node = nil
    
    while node do
        local type = node:type()
        if type:match("function") or type:match("method") then
            func_node = node
            break
        end
        node = node:parent()
    end
    
    local code
    if func_node then
        local start_row, _, end_row, _ = func_node:range()
        local lines = vim.api.nvim_buf_get_lines(0, start_row, end_row + 1, false)
        code = table.concat(lines, "\n")
    else
        -- Fall back to current paragraph
        vim.cmd("normal! vip")
        vim.cmd('normal! "xy')
        code = vim.fn.getreg("x")
        vim.cmd("normal! \\<Esc>")
    end
    
    local language = vim.bo.filetype
    
    vim.notify("[poor-cli] Generating tests...", vim.log.levels.INFO)
    
    rpc.request("poor-cli/chat", {
        message = "Generate unit tests for this " .. language .. " code. " ..
                  "Return ONLY the test code, no explanations.\n\n" ..
                  "```" .. language .. "\n" .. code .. "\n```"
    }, function(result, err)
        vim.schedule(function()
            if err then
                vim.notify("[poor-cli] Test generation failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                return
            end
            
            if result and result.content then
                -- Open a new split with the tests
                vim.cmd("below new")
                vim.bo.filetype = language
                
                local test_code = result.content
                test_code = test_code:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                
                local lines = vim.split(test_code, "\n", { plain = true })
                vim.api.nvim_buf_set_lines(0, 0, -1, false, lines)
                
                vim.notify("[poor-cli] Tests generated!", vim.log.levels.INFO)
            end
        end)
    end)
end

-- Generate documentation for current function
function M.generate_docs()
    local rpc = require("poor-cli.rpc")
    
    local node = vim.treesitter.get_node()
    local func_node = nil
    
    while node do
        local type = node:type()
        if type:match("function") or type:match("method") then
            func_node = node
            break
        end
        node = node:parent()
    end
    
    if not func_node then
        vim.notify("[poor-cli] Cursor not in a function", vim.log.levels.WARN)
        return
    end
    
    local start_row, _, end_row, _ = func_node:range()
    local lines = vim.api.nvim_buf_get_lines(0, start_row, end_row + 1, false)
    local code = table.concat(lines, "\n")
    local language = vim.bo.filetype
    
    vim.notify("[poor-cli] Generating docs...", vim.log.levels.INFO)
    
    rpc.request("poor-cli/chat", {
        message = "Generate a docstring/documentation comment for this " .. language .. " function. " ..
                  "Return ONLY the docstring, ready to be inserted above the function.\n\n" ..
                  "```" .. language .. "\n" .. code .. "\n```"
    }, function(result, err)
        vim.schedule(function()
            if err then
                vim.notify("[poor-cli] Doc generation failed: " .. vim.inspect(err), vim.log.levels.ERROR)
                return
            end
            
            if result and result.content then
                local docstring = result.content
                docstring = docstring:gsub("^```[%w]*\n", ""):gsub("\n```$", "")
                
                local doc_lines = vim.split(docstring, "\n", { plain = true })
                
                -- Insert above the function
                vim.api.nvim_buf_set_lines(0, start_row, start_row, false, doc_lines)
                
                vim.notify("[poor-cli] Docs generated!", vim.log.levels.INFO)
            end
        end)
    end)
end

return M
