-- test_inline.lua
-- Tests for poor-cli inline completion functionality

local inline = require("poor-cli.inline")
local rpc = require("poor-cli.rpc")
local config = require("poor-cli.config")

describe("poor-cli.inline", function()
    local original_config = nil

    before_each(function()
        original_config = vim.deepcopy(config.config)

        -- Clear any existing ghost text
        inline.clear_ghost_text()
        
        -- Create a fresh buffer
        _G.test_helpers.create_buffer({
            "function test()",
            "    local x = 1",
            "    ",
            "end",
        }, "lua")
    end)
    
    after_each(function()
        config.config = vim.deepcopy(original_config)
        _G.test_helpers.cleanup()
    end)
    
    describe("namespace", function()
        it("should have a valid namespace id", function()
            assert.is_not_nil(inline.ns_id)
            assert.is_number(inline.ns_id)
        end)
    end)
    
    describe("state management", function()
        it("should start with no completion", function()
            assert.is_nil(inline.current_completion)
            assert.is_false(inline.has_completion())
        end)
        
        it("should track completion state after showing ghost text", function()
            -- Move cursor to line 3
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            
            inline.show_ghost_text("return x + 1")
            
            assert.is_true(inline.has_completion())
            assert.is_not_nil(inline.current_completion)
            assert.are.equal("return x + 1", inline.current_completion.text)
        end)
        
        it("should clear completion state after clearing ghost text", function()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("test")
            
            inline.clear_ghost_text()
            
            assert.is_false(inline.has_completion())
            assert.is_nil(inline.current_completion)
        end)
    end)
    
    describe("show_ghost_text", function()
        it("should create extmark for single-line text", function()
            local bufnr = vim.api.nvim_get_current_buf()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            
            inline.show_ghost_text("return x")
            
            local marks = vim.api.nvim_buf_get_extmarks(bufnr, inline.ns_id, 0, -1, {})
            assert.are.equal(1, #marks)
        end)
        
        it("should not create extmark for empty text", function()
            local bufnr = vim.api.nvim_get_current_buf()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            
            inline.show_ghost_text("")
            
            local marks = vim.api.nvim_buf_get_extmarks(bufnr, inline.ns_id, 0, -1, {})
            assert.are.equal(0, #marks)
        end)
        
        it("should store correct cursor position", function()
            vim.api.nvim_win_set_cursor(0, { 2, 10 })
            
            inline.show_ghost_text("+ 1")
            
            assert.are.equal(1, inline.current_completion.line)  -- 0-indexed
            assert.are.equal(10, inline.current_completion.col)
        end)
    end)
    
    describe("clear_ghost_text", function()
        it("should remove all extmarks", function()
            local bufnr = vim.api.nvim_get_current_buf()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("test completion")
            
            inline.clear_ghost_text()
            
            local marks = vim.api.nvim_buf_get_extmarks(bufnr, inline.ns_id, 0, -1, {})
            assert.are.equal(0, #marks)
        end)
        
        it("should be safe to call multiple times", function()
            assert.has_no.errors(function()
                inline.clear_ghost_text()
                inline.clear_ghost_text()
                inline.clear_ghost_text()
            end)
        end)
    end)
    
    describe("accept", function()
        it("should return false when no completion active", function()
            local result = inline.accept()
            assert.is_false(result)
        end)
        
        it("should return true and insert text when completion active", function()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("return x + 1")
            
            local result = inline.accept()
            
            assert.is_true(result)
            
            -- Check that text was inserted
            local line = vim.api.nvim_buf_get_lines(0, 2, 3, false)[1]
            assert.matches("return x %+ 1", line)
        end)
        
        it("should clear ghost text after accepting", function()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("test")
            
            inline.accept()
            
            assert.is_false(inline.has_completion())
        end)
        
        it("should move cursor to end of inserted text", function()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("xyz")
            
            inline.accept()
            
            local cursor = vim.api.nvim_win_get_cursor(0)
            -- Cursor should be at column 7 (4 + 3 characters)
            assert.are.equal(7, cursor[2])
        end)
    end)
    
    describe("dismiss", function()
        it("should clear ghost text", function()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("test")
            
            inline.dismiss()
            
            assert.is_false(inline.has_completion())
        end)
        
        it("should not modify buffer content", function()
            local original = _G.test_helpers.get_buffer_content()
            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.show_ghost_text("extra text")
            
            inline.dismiss()
            
            local after = _G.test_helpers.get_buffer_content()
            assert.are.equal(original, after)
        end)
    end)

    describe("stale completion suppression", function()
        it("should ignore completion responses after cursor moves", function()
            local original_is_running = rpc.is_running
            local original_request = rpc.request
            local captured_callback = nil

            rpc.is_running = function()
                return true
            end
            rpc.request = function(_method, _params, callback)
                captured_callback = callback
                return 1
            end

            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.trigger()
            vim.api.nvim_win_set_cursor(0, { 3, 5 })

            captured_callback({ completion = "stale completion" }, nil)
            vim.wait(20)

            assert.is_false(inline.has_completion())

            rpc.is_running = original_is_running
            rpc.request = original_request
        end)

        it("should ignore older responses when a newer request exists", function()
            local original_is_running = rpc.is_running
            local original_request = rpc.request
            local callbacks = {}
            local next_id = 0

            rpc.is_running = function()
                return true
            end
            rpc.request = function(_method, _params, callback)
                next_id = next_id + 1
                callbacks[next_id] = callback
                return next_id
            end

            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.trigger()
            inline.trigger()

            callbacks[1]({ completion = "old completion" }, nil)
            callbacks[2]({ completion = "new completion" }, nil)
            vim.wait(20)

            assert.is_true(inline.has_completion())
            assert.are.equal("new completion", inline.current_completion.text)

            rpc.is_running = original_is_running
            rpc.request = original_request
        end)
    end)

    describe("completion controls", function()
        it("should block auto-triggered completions in manual-only mode", function()
            config.config.completion_manual_only = true

            local enabled, reason = inline.is_enabled_for_buffer(0, { manual = false })
            local manual_enabled = inline.is_enabled_for_buffer(0, { manual = true })

            assert.is_false(enabled)
            assert.are.equal("manual only", reason)
            assert.is_true(manual_enabled)
        end)

        it("should shape completion requests within configured budgets", function()
            _G.test_helpers.create_buffer({
                "local alpha = '1234567890'",
                "local beta = alpha .. alpha",
                "return alpha .. beta",
            }, "lua")
            vim.api.nvim_win_set_cursor(0, { 2, 12 })

            config.config.completion_max_lines_before = 1
            config.config.completion_max_lines_after = 1
            config.config.completion_max_chars = 18
            config.config.completion_lsp_context_max_chars = 0
            config.config.completion_provider = "openai"
            config.config.completion_model = "gpt-5-codex"
            config.config.completion_stream_partial = true

            local payload = inline.build_completion_request({
                bufnr = 0,
                line = 2,
                col = 12,
                request_id = "inline-budget",
                instruction = "continue",
            })

            assert.is_true(#payload.codeBefore <= 10)
            assert.is_true(#payload.codeAfter <= 8)
            assert.are.equal("inline-budget", payload.requestId)
            assert.are.equal("openai", payload.provider)
            assert.are.equal("gpt-5-codex", payload.model)
            assert.is_true(payload.streamPartial)
        end)
    end)

    describe("partial streaming", function()
        it("should render partial chunks for the active request", function()
            local original_is_running = rpc.is_running
            local original_request = rpc.request

            rpc.is_running = function()
                return true
            end
            rpc.request = function(_method, _params, callback)
                return 21
            end

            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.trigger({ manual = true })

            local request_id = inline.pending_inline_request.request_id
            vim.api.nvim_exec_autocmds("User", {
                pattern = "PoorCliInlineChunk",
                data = {
                    request_id = request_id,
                    chunk = "return x + 1",
                    done = false,
                },
            })

            vim.wait(20, function()
                return inline.has_completion()
            end)

            assert.is_true(inline.has_completion())
            assert.are.equal("return x + 1", inline.current_completion.text)

            rpc.is_running = original_is_running
            rpc.request = original_request
        end)

        it("should ignore partial chunks from stale request ids", function()
            local original_is_running = rpc.is_running
            local original_request = rpc.request

            rpc.is_running = function()
                return true
            end
            rpc.request = function(_method, _params, callback)
                return 22
            end

            vim.api.nvim_win_set_cursor(0, { 3, 4 })
            inline.trigger({ manual = true })

            vim.api.nvim_exec_autocmds("User", {
                pattern = "PoorCliInlineChunk",
                data = {
                    request_id = "stale-request",
                    chunk = "wrong completion",
                    done = false,
                },
            })
            vim.wait(20)

            assert.is_false(inline.has_completion())

            rpc.is_running = original_is_running
            rpc.request = original_request
        end)
    end)
    
    describe("has_completion", function()
        it("should return false initially", function()
            assert.is_false(inline.has_completion())
        end)
        
        it("should return true after showing ghost text", function()
            vim.api.nvim_win_set_cursor(0, { 1, 0 })
            inline.show_ghost_text("test")
            
            assert.is_true(inline.has_completion())
        end)
        
        it("should return false after dismiss", function()
            vim.api.nvim_win_set_cursor(0, { 1, 0 })
            inline.show_ghost_text("test")
            inline.dismiss()
            
            assert.is_false(inline.has_completion())
        end)
        
        it("should return false after accept", function()
            vim.api.nvim_win_set_cursor(0, { 1, 0 })
            inline.show_ghost_text("t")
            inline.accept()
            
            assert.is_false(inline.has_completion())
        end)
    end)
end)
