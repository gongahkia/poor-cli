local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("autocmds", function()
    local callbacks
    local original_create_autocmd
    local original_create_augroup

    before_each(function()
        callbacks = {}
        original_create_autocmd = vim.api.nvim_create_autocmd
        original_create_augroup = vim.api.nvim_create_augroup
        vim.api.nvim_create_augroup = function()
            return 1
        end
        vim.api.nvim_create_autocmd = function(event, opts)
            callbacks[event] = opts.callback
            return 1
        end
        package.loaded["poor-cli.autocmds"] = nil
    end)

    after_each(function()
        vim.api.nvim_create_autocmd = original_create_autocmd
        vim.api.nvim_create_augroup = original_create_augroup
        package.loaded["poor-cli.autocmds"] = nil
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.inline"] = nil
    end)

    local function install_stubs(rpc_stub)
        package.loaded["poor-cli.config"] = { get = function() return false end }
        package.loaded["poor-cli.rpc"] = rpc_stub
        package.loaded["poor-cli.inline"] = {
            cancel_auto_trigger = function() end,
            cancel_active_request = function() end,
            clear_ghost_text = function() end,
        }
    end

    it("uses stop_for_exit when available", function()
        local calls = { stop_for_exit = 0, stop = 0 }
        install_stubs({
            is_running = function() return true end,
            stop_for_exit = function() calls.stop_for_exit = calls.stop_for_exit + 1 end,
            stop = function() calls.stop = calls.stop + 1 end,
        })

        require("poor-cli.autocmds").setup()
        callbacks["VimLeavePre"]()

        assert.are.equal(1, calls.stop_for_exit)
        assert.are.equal(0, calls.stop)
    end)

    it("falls back to stop when stop_for_exit is unavailable", function()
        local calls = { stop = 0 }
        install_stubs({
            is_running = function() return true end,
            stop = function() calls.stop = calls.stop + 1 end,
        })

        require("poor-cli.autocmds").setup()
        callbacks["VimLeavePre"]()

        assert.are.equal(1, calls.stop)
    end)
end)
