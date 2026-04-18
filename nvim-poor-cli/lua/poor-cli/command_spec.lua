-- poor-cli/command_spec.lua
-- Single source of truth for noun-first :PoorCLI<Noun> <verb> [args] commands.
--
-- Each noun module registers one dispatcher per noun via dispatch(), passing its
-- spec. The spec lives here so that:
--   1. completion (verb list, arg list) has one implementation
--   2. :PoorCLIPalette can enumerate noun+verb pairs for fuzzy search
--   3. usage strings stay in sync with the handler table

local M = {}

-- Noun spec registry. Populated by each noun module at setup() time via
-- M.register(noun_key, spec). We do not pre-populate here — that would require
-- this module to depend on every feature module, breaking lazy-loading.
M._specs = {}

-- Pending extends: if extend() is called on a noun before install(), the
-- partial is queued here and replayed when install() happens. Fixes the
-- EAGER_SETUPS ordering hazard in init.lua (commands runs first but extends
-- nouns that later modules install).
M._pending_extends = {}
M._bootstraps = {}
M._bootstrap_done = {}

-- register associates a noun key (lowercase, matches :PoorCLI<Noun>) with its
-- spec table. Called from each noun module.
--
-- spec shape:
--   desc        = string  -- command description
--   verb_names  = { "list", "create", ... }   -- ordered; drives completion + usage
--   verbs       = { list = function(fargs, opts) end, ... }
--                 fargs: verb-stripped args (e.g. :PoorCLITask show ID → fargs = {"ID"})
--                 opts:  original nvim command opts (range, line1, line2, bang, ...)
--   arg_complete = { [verb] = function(arg_lead) return {...} end, ... } -- optional
function M.register(noun, spec)
    assert(type(noun) == "string" and noun ~= "", "noun key required")
    assert(type(spec) == "table", "spec table required")
    assert(type(spec.verbs) == "table", "spec.verbs required")
    assert(type(spec.verb_names) == "table", "spec.verb_names required")
    M._specs[noun] = spec
end

-- get retrieves the spec for a noun. Returns nil if unregistered.
function M.get(noun) return M._specs[noun] end

-- all returns the full registry (for palette / debug).
function M.all() return M._specs end

-- make_complete returns a Neovim completion function bound to a noun key.
-- Complete returns verb names when the user is typing the verb token,
-- delegates to arg_complete[verb] for subsequent arguments, or {} otherwise.
function M.make_complete(noun)
    return function(arg_lead, cmd_line, _)
        if M._run_bootstrap then
            M._run_bootstrap(noun)
        end
        local spec = M._specs[noun]
        if not spec then return {} end
        -- Split cmd_line; first token is the :Command name, rest are args.
        local parts = vim.split(cmd_line or "", "%s+", { trimempty = true })
        -- parts[1] = "PoorCLI<Noun>"; parts[2] = verb; parts[3..] = args
        local arg_count = #parts - 1
        -- Trailing space means user is typing the NEXT token.
        local trailing_space = cmd_line and cmd_line:sub(-1) == " "
        local completing_idx = trailing_space and (arg_count + 1) or arg_count
        if completing_idx <= 1 then
            -- Completing the verb.
            local out = {}
            for _, v in ipairs(spec.verb_names) do
                if v:find("^" .. vim.pesc(arg_lead or "")) then
                    table.insert(out, v)
                end
            end
            return out
        end
        local verb = parts[2]
        local arg_fn = (spec.arg_complete or {})[verb]
        if not arg_fn then return {} end
        local ok, items = pcall(arg_fn, arg_lead, parts)
        if not ok or type(items) ~= "table" then return {} end
        return items
    end
end

-- dispatch builds a function body suitable for nvim_create_user_command's
-- callback. It parses opts.fargs, looks up the verb handler, and dispatches.
-- Unknown verbs get a usage notification listing the valid verbs.
function M.dispatch(noun)
    return function(opts)
        if M._run_bootstrap then
            M._run_bootstrap(noun)
        end
        local spec = M._specs[noun]
        if not spec then
            vim.notify(
                "[poor-cli] noun '" .. noun .. "' not registered; did a module fail to load?",
                vim.log.levels.ERROR
            )
            return
        end
        local fargs = opts.fargs or {}
        local verb = fargs[1]
        if not verb or verb == "" then
            vim.notify(
                "[poor-cli] usage: :PoorCLI" .. _capitalize(noun)
                    .. " {" .. table.concat(spec.verb_names, "|") .. "}",
                vim.log.levels.WARN
            )
            return
        end
        local handler = spec.verbs[verb]
        if not handler then
            if M._run_bootstrap then
                M._run_bootstrap(noun, verb)
                spec = M._specs[noun]
                handler = spec and spec.verbs and spec.verbs[verb] or nil
            end
        end
        if not handler then
            vim.notify(
                "[poor-cli] unknown verb '" .. verb .. "' for :PoorCLI" .. _capitalize(noun)
                    .. "; valid: " .. table.concat(spec.verb_names, ", "),
                vim.log.levels.WARN
            )
            return
        end
        -- Forward verb-stripped args plus original opts (range/line1/line2/bang).
        local rest = {}
        for i = 2, #fargs do rest[i - 1] = fargs[i] end
        return handler(rest, opts)
    end
end

function M.bootstrap(noun, loader)
    assert(type(noun) == "string" and noun ~= "", "noun key required")
    assert(type(loader) == "function", "loader function required")
    M._bootstraps[noun] = M._bootstraps[noun] or {}
    table.insert(M._bootstraps[noun], loader)
end

function M._run_bootstrap(noun, verb)
    local loaders = M._bootstraps[noun]
    if type(loaders) ~= "table" or #loaders == 0 then
        return false
    end
    if M._bootstrap_done[noun] then
        return false
    end
    M._bootstrap_done[noun] = true
    for _, loader in ipairs(loaders) do
        pcall(loader, verb)
    end
    return true
end

-- Capitalize first letter (for usage messages). "task" → "Task".
function _capitalize(s)
    if not s or s == "" then return s end
    return s:sub(1, 1):upper() .. s:sub(2)
end
M._capitalize = _capitalize  -- exported for tests

-- Convenience: register a noun AND install its :PoorCLI<Noun> command in one call.
-- Returns the spec so callers can chain if desired.
-- create_cmd defaults to vim.api.nvim_create_user_command but is injectable
-- for tests that need to capture registrations.
function M.install(noun, spec, create_cmd)
    M.register(noun, spec)
    local name = "PoorCLI" .. _capitalize(noun)
    local create = create_cmd or vim.api.nvim_create_user_command
    pcall(vim.api.nvim_del_user_command, name)
    create(name, M.dispatch(noun), {
        nargs = "*",
        range = spec.range and true or nil,
        bang = spec.bang and true or nil,
        desc = spec.desc,
        complete = M.make_complete(noun),
    })
    -- Replay any extends that were queued before this install.
    local queued = M._pending_extends[noun]
    if queued then
        M._pending_extends[noun] = nil
        for _, partial in ipairs(queued) do M.extend(noun, partial) end
    end
end

-- Extend an already-registered noun with additional verbs. Used when a noun's
-- verbs are defined across multiple modules (e.g. Config has verbs in
-- config_mgr.lua and commands.lua). The :PoorCLI<Noun> command must already
-- have been installed by one module (the "owner") before any other module
-- calls extend(). New verb_names are appended in order; duplicates overwrite.
--
-- opts.verb_prefix (v6.2): string prepended to every verb name in the partial
-- spec before merging. Lets absorbed nouns register their verbs under a new
-- noun without name collisions. Example: during v6.2 collapse, history_browser
-- calls spec.extend("chat", { verb_prefix = "history-", verbs = { list = ... } })
-- which registers verb "history-list" on the chat noun.
function M.extend(noun, partial)
    assert(type(partial) == "table", "partial spec required")
    local spec = M._specs[noun]
    if not spec then
        -- Queue for replay at install time. The EAGER_SETUPS ordering in
        -- init.lua may call extend() before the owning module's install().
        M._pending_extends[noun] = M._pending_extends[noun] or {}
        table.insert(M._pending_extends[noun], partial)
        return
    end
    local prefix = partial.verb_prefix or ""
    if partial.verbs then
        for verb, handler in pairs(partial.verbs) do
            local name = prefix .. verb
            if not spec.verbs[name] then
                table.insert(spec.verb_names, name)
            end
            spec.verbs[name] = handler
        end
    end
    if partial.verb_names then
        -- Honor an explicit verb_names list when the caller wants to override
        -- the pairs()-order for completion. Prefixed identically.
        for _, verb in ipairs(partial.verb_names) do
            local name = prefix .. verb
            local seen = false
            for _, existing in ipairs(spec.verb_names) do
                if existing == name then seen = true; break end
            end
            if not seen then table.insert(spec.verb_names, name) end
        end
    end
    if partial.arg_complete then
        spec.arg_complete = spec.arg_complete or {}
        for verb, fn in pairs(partial.arg_complete) do
            spec.arg_complete[prefix .. verb] = fn
        end
    end
end

-- Alias for tests — reads the underlying registry without exposing internals.
M._registry = M._specs

return M
