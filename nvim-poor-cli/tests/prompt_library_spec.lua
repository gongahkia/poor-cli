local root = vim.fn.fnamemodify(debug.getinfo(1, "S").source:sub(2), ":p:h:h")
package.path = root .. "/lua/?.lua;" .. root .. "/lua/?/init.lua;" .. package.path

describe("prompt library", function()
    local lib

    before_each(function()
        package.loaded["poor-cli.rpc"] = { request = function() end, format_error = function(err) return tostring(err) end }
        package.loaded["poor-cli.config"] = { get = function() return nil end }
        package.loaded["poor-cli.prompt_library"] = nil
        lib = require("poor-cli.prompt_library")
    end)

    after_each(function()
        package.loaded["poor-cli.rpc"] = nil
        package.loaded["poor-cli.config"] = nil
        package.loaded["poor-cli.chat"] = nil
        package.loaded["poor-cli.pickers"] = nil
        package.loaded["poor-cli.prompt_library"] = nil
    end)

    it("parses front matter title tags and body", function()
        local prompt = lib.parse_front_matter(table.concat({
            "---",
            "title: Review Diff",
            "tags:",
            "  - git",
            "  - review",
            "description: Check staged changes",
            "---",
            "Review this diff.",
        }, "\n"), "/tmp/review.md")
        assert.are.equal("Review Diff", prompt.title)
        assert.are.equal("Check staged changes", prompt.description)
        assert.are.equal("git", prompt.tags[1])
        assert.are.equal("review", prompt.tags[2])
        assert.are.equal("Review this diff.", prompt.body)
    end)

    it("loads markdown prompts from override dir", function()
        local dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        vim.fn.writefile({ "---", "title: Alpha", "tags: [one, two]", "---", "body" }, vim.fs.joinpath(dir, "alpha.md"))
        vim.fn.writefile({ "ignored" }, vim.fs.joinpath(dir, "skip.txt"))
        local prompts = lib.load_prompts({ prompt_dir = dir })
        assert.are.equal(1, #prompts)
        assert.are.equal("Alpha", prompts[1].title)
        assert.are.equal("one", prompts[1].tags[1])
        vim.fn.delete(dir, "rf")
    end)

    it("dispatches run edit delete and clone actions", function()
        local calls = {}
        local dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        local path = vim.fs.joinpath(dir, "a.md")
        local prompt = lib.parse_front_matter("---\ntitle: A\ntags: [x]\n---\nBody", path)

        lib.dispatch_action("run", prompt, { run = function(p) table.insert(calls, { "run", p.body }) end })
        lib.dispatch_action("edit", prompt, { edit = function(p) table.insert(calls, { "edit", p.path }) end })
        lib.dispatch_action("delete", prompt, {
            confirm = function(p) table.insert(calls, { "confirm", p.title }); return true end,
            remove = function(p) table.insert(calls, { "delete", p.path }) end,
        })
        lib.dispatch_action("clone", prompt, {
            input = function(default, cb) table.insert(calls, { "input", default }); cb("a-copy") end,
            clone = function(p, clone_path, name) table.insert(calls, { "clone", p.title, clone_path, name }) end,
        })

        assert.are.equal("run", calls[1][1])
        assert.are.equal("edit", calls[2][1])
        assert.are.equal("confirm", calls[3][1])
        assert.are.equal("delete", calls[4][1])
        assert.are.equal("input", calls[5][1])
        assert.are.equal("clone", calls[6][1])
        assert.are.equal("a-copy", calls[6][4])
        vim.fn.delete(dir, "rf")
    end)

    it("opens picker with title and tag-searchable labels", function()
        local dir = vim.fn.tempname()
        vim.fn.mkdir(dir, "p")
        vim.fn.writefile({ "---", "title: Beta", "tags: [git]", "---", "body" }, vim.fs.joinpath(dir, "beta.md"))
        local seen
        package.loaded["poor-cli.pickers"] = {
            pick = function(items, opts)
                seen = { items = items, opts = opts }
            end,
        }
        lib.open({ prompt_dir = dir })
        assert.are.equal("Prompt Library", seen.opts.title)
        assert.truthy(seen.items[1].label:find("Beta", 1, true))
        assert.truthy(seen.items[1].search:find("git", 1, true))
        vim.fn.delete(dir, "rf")
    end)
end)
