local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("dap bridge", function()
    local old_preload
    local calls
    local notifies
    local tmp
    local bufs

    local function clear_modules()
        for _, name in ipairs({
            "dap",
            "poor-cli.config",
            "poor-cli.notify",
            "poor-cli.diagnostics",
            "poor-cli.integrations.dap",
        }) do
            package.loaded[name] = nil
        end
    end

    local function install_config(opts)
        package.loaded["poor-cli.config"] = {
            get = function(key)
                if key == "dap" then
                    return opts or { keymaps_enabled = true, breakpoint_key = "<leader>pb", run_key = "<leader>pB" }
                end
                return nil
            end,
        }
        package.loaded["poor-cli.notify"] = {
            notify = function(msg, level)
                table.insert(notifies, { msg = msg, level = level })
            end,
        }
    end

    local function install_dap(opts)
        opts = opts or {}
        package.preload["dap"] = function()
            return {
                toggle_breakpoint = function()
                    table.insert(calls.breakpoints, {
                        path = vim.api.nvim_buf_get_name(0),
                        line = vim.api.nvim_win_get_cursor(0)[1],
                    })
                end,
                continue = function()
                    if opts.continue_error then error(opts.continue_error) end
                    calls.continues = calls.continues + 1
                end,
            }
        end
    end

    local function ref_buf(line)
        local buf = vim.api.nvim_create_buf(false, true)
        table.insert(bufs, buf)
        vim.bo[buf].filetype = "markdown"
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "see " .. tmp .. ":" .. line })
        vim.api.nvim_set_current_buf(buf)
        vim.api.nvim_win_set_cursor(0, { 1, 4 })
        return buf
    end

    before_each(function()
        calls = { breakpoints = {}, continues = 0 }
        notifies = {}
        bufs = {}
        tmp = vim.fn.fnamemodify(vim.fn.tempname(), ":p")
        vim.fn.writefile({ "one", "two", "three" }, tmp)
        tmp = (vim.uv or vim.loop).fs_realpath(tmp) or tmp
        old_preload = package.preload["dap"]
        clear_modules()
        install_config()
    end)

    after_each(function()
        vim.diagnostic.reset()
        for _, buf in ipairs(bufs) do
            if vim.api.nvim_buf_is_valid(buf) then
                pcall(vim.api.nvim_buf_delete, buf, { force = true })
            end
        end
        local file_buf = vim.fn.bufnr(tmp)
        if file_buf ~= -1 then pcall(vim.api.nvim_buf_delete, file_buf, { force = true }) end
        vim.fn.delete(tmp)
        package.preload["dap"] = old_preload
        clear_modules()
    end)

    it("test_breakpoint_set_at_line", function()
        install_dap()
        ref_buf(2)
        local bridge = require("poor-cli.integrations.dap")

        assert.is_true(bridge.set_breakpoint())
        assert.are.equal(1, #calls.breakpoints)
        assert.are.equal(tmp, calls.breakpoints[1].path)
        assert.are.equal(2, calls.breakpoints[1].line)
    end)

    it("sets_breakpoint_from_diagnostic_message", function()
        install_dap()
        local diagnostics = require("poor-cli.diagnostics")
        local buf = vim.api.nvim_create_buf(false, true)
        table.insert(bufs, buf)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, { "diagnostic host" })
        vim.api.nvim_set_current_buf(buf)
        vim.api.nvim_win_set_cursor(0, { 1, 0 })
        vim.diagnostic.set(diagnostics.ns, buf, {
            { lnum = 0, col = 0, message = tmp .. ":3: bug", severity = vim.diagnostic.severity.HINT },
        })

        local bridge = require("poor-cli.integrations.dap")
        assert.is_true(bridge.set_breakpoint())
        assert.are.equal(tmp, calls.breakpoints[1].path)
        assert.are.equal(3, calls.breakpoints[1].line)
    end)

    it("runs_continue_after_breakpoint", function()
        install_dap()
        ref_buf(1)
        local bridge = require("poor-cli.integrations.dap")

        assert.is_true(bridge.run())
        assert.are.equal(1, #calls.breakpoints)
        assert.are.equal(1, calls.continues)
    end)

    it("handles_missing_dap_configuration", function()
        install_dap({ continue_error = "no configuration" })
        ref_buf(1)
        local bridge = require("poor-cli.integrations.dap")

        assert.is_false(bridge.run())
        assert.are.equal(1, #calls.breakpoints)
        assert.are.equal(1, #notifies)
        assert.truthy(notifies[1].msg:find("no configuration", 1, true))
    end)

    it("test_noop_when_dap_absent", function()
        package.preload["dap"] = function() error("no dap") end
        local buf = ref_buf(2)
        local bridge = require("poor-cli.integrations.dap")

        assert.is_false(bridge.setup())
        assert.is_false(bridge.attach(buf))
        assert.is_false(bridge.set_breakpoint())
        assert.are.equal(0, #calls.breakpoints)

        local maps = vim.api.nvim_buf_get_keymap(buf, "n")
        for _, map in ipairs(maps) do
            assert.are_not.equal("<leader>pb", map.lhs)
        end
    end)
end)
