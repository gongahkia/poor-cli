-- test_inline.lua
-- Tests for poor-cli inline completion functionality

local inline = require("poor-cli.inline")

describe("poor-cli.inline", function()
    before_each(function()
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
