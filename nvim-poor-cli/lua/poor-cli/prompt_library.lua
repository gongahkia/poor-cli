local rpc = require("poor-cli.rpc")
local M = {}

function M.save(params, callback) return rpc.request("poor-cli/promptSave", params or {}, callback) end
function M.load(params, callback) return rpc.request("poor-cli/promptLoad", params or {}, callback) end
function M.list(params, callback) return rpc.request("poor-cli/promptList", params or {}, callback) end
function M.delete(params, callback) return rpc.request("poor-cli/promptDelete", params or {}, callback) end

local function trim(text)
    return tostring(text or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function strip_quotes(text)
    text = trim(text)
    local first = text:sub(1, 1)
    if (first == '"' or first == "'") and text:sub(-1) == first then
        return text:sub(2, -2)
    end
    return text
end

local function parse_scalar(value)
    value = trim(value)
    if value:sub(1, 1) == "[" and value:sub(-1) == "]" then
        local out = {}
        for item in value:sub(2, -2):gmatch("[^,]+") do
            table.insert(out, strip_quotes(item))
        end
        return out
    end
    return strip_quotes(value)
end

local function basename_without_ext(path)
    return vim.fn.fnamemodify(path or "", ":t:r")
end

local function normalize_tags(tags)
    if type(tags) == "table" then return tags end
    if type(tags) ~= "string" or tags == "" then return {} end
    local out = {}
    for item in tags:gmatch("[^,]+") do table.insert(out, trim(item)) end
    return out
end

function M.parse_front_matter(text, path)
    text = tostring(text or "")
    local metadata = {}
    local body = text
    local front = text:match("^%-%-%-%s*\r?\n(.-)\r?\n%-%-%-%s*\r?\n?(.*)$")
    if front then
        local body_match
        front, body_match = text:match("^%-%-%-%s*\r?\n(.-)\r?\n%-%-%-%s*\r?\n?(.*)$")
        body = body_match or ""
        local list_key
        for line in front:gmatch("[^\r\n]+") do
            local key, value = line:match("^([%w_-]+):%s*(.-)%s*$")
            if key then
                if value == "" then
                    metadata[key] = {}
                    list_key = key
                else
                    metadata[key] = parse_scalar(value)
                    list_key = nil
                end
            elseif list_key then
                local item = line:match("^%s*%-%s*(.-)%s*$")
                if item then table.insert(metadata[list_key], strip_quotes(item)) end
            end
        end
    end
    metadata.tags = normalize_tags(metadata.tags)
    return {
        id = basename_without_ext(path),
        path = path,
        title = metadata.title or basename_without_ext(path),
        description = metadata.description or "",
        tags = metadata.tags,
        metadata = metadata,
        body = body,
        raw = text,
    }
end

function M.prompt_dir(opts)
    opts = opts or {}
    if opts.prompt_dir and opts.prompt_dir ~= "" then return vim.fn.fnamemodify(opts.prompt_dir, ":p") end
    local config = require("poor-cli.config")
    local configured = config.get("prompt_dir")
    if configured and configured ~= "" then return vim.fn.fnamemodify(configured, ":p") end
    return vim.fs.joinpath(vim.fn.getcwd(), ".poor-cli", "prompts")
end

function M.load_prompts(opts)
    local dir = M.prompt_dir(opts)
    local paths = vim.fn.glob(vim.fs.joinpath(dir, "*.md"), false, true)
    table.sort(paths)
    local prompts = {}
    for _, path in ipairs(paths) do
        local file = io.open(path, "r")
        if file then
            local text = file:read("*a")
            file:close()
            table.insert(prompts, M.parse_front_matter(text, path))
        end
    end
    return prompts
end

local function render_preview(prompt)
    local tags = #prompt.tags > 0 and table.concat(prompt.tags, ", ") or "none"
    local lines = { "# " .. prompt.title, "", "Tags: " .. tags }
    if prompt.description ~= "" then
        table.insert(lines, "Description: " .. prompt.description)
    end
    table.insert(lines, "")
    table.insert(lines, prompt.body)
    return table.concat(lines, "\n")
end

function M.to_picker_items(prompts)
    local items = {}
    for _, prompt in ipairs(prompts or {}) do
        local tag_text = table.concat(prompt.tags, " ")
        table.insert(items, {
            id = prompt.id,
            label = prompt.title .. (#prompt.tags > 0 and (" [" .. table.concat(prompt.tags, ",") .. "]") or ""),
            search = prompt.title .. " " .. tag_text,
            preview = render_preview(prompt),
            data = prompt,
        })
    end
    return items
end

local function write_prompt(path, prompt, title)
    local meta = vim.deepcopy(prompt.metadata or {})
    meta.title = title or meta.title or prompt.title
    local lines = { "---" }
    for key, value in pairs(meta) do
        if key ~= "tags" and type(value) ~= "table" then
            table.insert(lines, key .. ": " .. tostring(value))
        end
    end
    table.insert(lines, "tags:")
    for _, tag in ipairs(normalize_tags(meta.tags)) do table.insert(lines, "  - " .. tag) end
    table.insert(lines, "---")
    table.insert(lines, prompt.body or "")
    vim.fn.writefile(lines, path)
end

function M.dispatch_action(action, prompt, opts)
    opts = opts or {}
    if type(prompt) ~= "table" then return end
    action = action or "run"
    if action == "default" then action = "run" end
    if action == "run" then
        if opts.run then return opts.run(prompt) end
        require("poor-cli.chat").send(prompt.body)
        return
    end
    if action == "edit" or action == "e" then
        if opts.edit then return opts.edit(prompt) end
        vim.cmd("edit " .. vim.fn.fnameescape(prompt.path))
        return
    end
    if action == "delete" or action == "d" then
        local confirm = opts.confirm or function(p)
            return vim.fn.confirm("Delete prompt " .. p.title .. "?", "&Delete\n&Cancel", 2) == 1
        end
        if not confirm(prompt) then return end
        if opts.remove then return opts.remove(prompt) end
        local ok = vim.fn.delete(prompt.path) == 0
        if ok then require("poor-cli.notify").notify("[poor-cli] prompt deleted: " .. prompt.title, vim.log.levels.INFO) end
        return ok
    end
    if action == "clone" or action == "<C-n>" then
        local input = opts.input or function(default, cb)
            vim.ui.input({ prompt = "Clone prompt as: ", default = default }, cb)
        end
        input(prompt.id .. "-copy", function(name)
            name = trim(name)
            if name == "" then return end
            local path = vim.fs.joinpath(vim.fn.fnamemodify(prompt.path, ":h"), name .. ".md")
            if opts.clone then return opts.clone(prompt, path, name) end
            write_prompt(path, prompt, name)
            require("poor-cli.notify").notify("[poor-cli] prompt cloned: " .. name, vim.log.levels.INFO)
        end)
    end
end

function M.open(opts)
    opts = opts or {}
    local pickers = require("poor-cli.pickers")
    local prompts = M.load_prompts(opts)
    if #prompts == 0 then
        require("poor-cli.notify").notify("[poor-cli] no saved prompts in " .. M.prompt_dir(opts), vim.log.levels.INFO)
        return
    end
    pickers.pick(M.to_picker_items(prompts), {
        title = "Prompt Library",
        on_pick = function(prompt) M.dispatch_action("run", prompt) end,
        actions = {
            e = function(prompt) M.dispatch_action("edit", prompt) end,
            d = function(prompt) M.dispatch_action("delete", prompt) end,
            ["<C-n>"] = function(prompt) M.dispatch_action("clone", prompt) end,
        },
    })
end

function M.setup()
    local function create_command(name, fn, opts) pcall(vim.api.nvim_del_user_command, name); vim.api.nvim_create_user_command(name, fn, opts or {}) end
    create_command("PoorCLIPromptList", function() M.open() end, { desc = "Browse saved prompts" })
    create_command("PoorCLIPromptSave", function()
        vim.ui.input({ prompt = "Prompt name: " }, function(name)
            if not name or name == "" then return end
            vim.ui.input({ prompt = "Prompt content: " }, function(content)
                if not content or content == "" then return end
                M.save({ name = name, content = content }, function(_, err) vim.schedule(function()
                    if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
                    else require("poor-cli.notify").notify("[poor-cli] prompt saved: " .. name, vim.log.levels.INFO) end
                end) end)
            end)
        end)
    end, { desc = "Save a prompt" })
    create_command("PoorCLIPromptLoad", function(opts)
        M.load({ name = opts.args }, function(result, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR); return end
            local buf = vim.api.nvim_create_buf(false, true)
            vim.bo[buf].buftype = "nofile"
            vim.bo[buf].bufhidden = "wipe"
            vim.bo[buf].filetype = "markdown"
            vim.api.nvim_buf_set_name(buf, "[poor-cli prompt " .. opts.args .. "]")
            vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split((result or {}).content or "", "\n", { plain = true }))
            vim.cmd("botright split")
            vim.api.nvim_win_set_buf(0, buf)
        end) end)
    end, { nargs = 1, desc = "Load a saved prompt" })
    create_command("PoorCLIPromptDelete", function(opts)
        M.delete({ name = opts.args }, function(_, err) vim.schedule(function()
            if err then require("poor-cli.notify").notify("[poor-cli] " .. rpc.format_error(err), vim.log.levels.ERROR)
            else require("poor-cli.notify").notify("[poor-cli] prompt deleted: " .. opts.args, vim.log.levels.INFO) end
        end) end)
    end, { nargs = 1, desc = "Delete a saved prompt" })
end

return M
