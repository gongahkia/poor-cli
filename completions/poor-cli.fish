# Fish completion for poor-cli
# Copy to ~/.config/fish/completions/poor-cli.fish

complete -c poor-cli -e
complete -c poor-cli-sync -e

# Root command surface
complete -c poor-cli -f -n "__fish_use_subcommand" -a "help" -d "Show root help"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "version" -d "Print version"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "tui" -d "Launch Rust TUI"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "install" -d "Run installer wizard"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "install-info" -d "Inspect launcher selection"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "exec" -d "Run one shared-core request"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "task" -d "Manage durable tasks"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "automation" -d "Manage AutomationRule triggers"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "github-task" -d "Create task from GitHub event"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "skills" -d "List and run skills"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "commands" -d "Legacy alias for slash-trigger AutomationRules"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "server" -d "Run JSON-RPC server"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "telegram" -d "Run Telegram bot frontend"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "watch" -d "Watch files for inline instructions"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "deploy" -d "Deploy project"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "preview" -d "Run preview server"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "review-pr" -d "Review GitHub PR"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "agent" -d "Manage background agents"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "checkpoint" -d "Manage checkpoints"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "history" -d "Search and export history"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "session" -d "Manage sessions"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "memory" -d "Manage memory entries"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "config" -d "Manage configuration"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "profile" -d "List and apply profiles"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "trust" -d "Manage repository trust"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "provider" -d "List and switch providers"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "doctor" -d "Run diagnostics"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "status" -d "Show session status"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "policy" -d "Show policy status"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "tools" -d "List available tools"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "mcp" -d "Show MCP status"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "cost" -d "Show cost and economy"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "audit" -d "Export or rotate audit logs"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "search" -d "Search the codebase"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "review" -d "Review file or staged diff"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "commit" -d "Generate commit message"

# Nested subcommands
complete -c poor-cli -f -n "__fish_seen_subcommand_from task" -a "create list show start wait approve cancel retry replay run"
complete -c poor-cli -f -n "__fish_seen_subcommand_from automation" -a "create list show enable disable run-now run-due serve history replay migrate"
complete -c poor-cli -f -n "__fish_seen_subcommand_from agent" -a "start list logs result cancel run"
complete -c poor-cli -f -n "__fish_seen_subcommand_from skills" -a "list show run"
complete -c poor-cli -f -n "__fish_seen_subcommand_from commands" -a "list show run"
complete -c poor-cli -f -n "__fish_seen_subcommand_from github-task" -a "create"
complete -c poor-cli -f -n "__fish_seen_subcommand_from telegram" -a "setup"
complete -c poor-cli -f -n "__fish_seen_subcommand_from checkpoint" -a "list create preview restore"
complete -c poor-cli -f -n "__fish_seen_subcommand_from history" -a "list search export"
complete -c poor-cli -f -n "__fish_seen_subcommand_from session" -a "list create fork destroy"
complete -c poor-cli -f -n "__fish_seen_subcommand_from memory" -a "list save search delete"
complete -c poor-cli -f -n "__fish_seen_subcommand_from config" -a "list get set toggle"
complete -c poor-cli -f -n "__fish_seen_subcommand_from profile" -a "list apply"
complete -c poor-cli -f -n "__fish_seen_subcommand_from trust" -a "status trust untrust"
complete -c poor-cli -f -n "__fish_seen_subcommand_from provider" -a "list info switch"
complete -c poor-cli -f -n "__fish_seen_subcommand_from cost" -a "summary economy savings"
complete -c poor-cli -f -n "__fish_seen_subcommand_from audit" -a "export rotate"
complete -c poor-cli -f -n "__fish_seen_subcommand_from search" -a "index stats"

# exec
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l prompt -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l output-format -r -a "text json stream-json"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l resume
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l allow-tool -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l deny-tool -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l plan-only
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l provider -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l model -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l routing-mode -r -a "manual quality speed cheap private"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l api-key -r
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l cwd -r -a "(__fish_complete_directories)"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l sandbox-preset -r -a "read-only review-only workspace-write full-access"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l permission-mode -r -a "prompt auto-safe danger-full-access"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l auto-approve
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l pinned-context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from exec" -l context-budget-tokens -r

# task create
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l title -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l prompt -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l preset -r -a "read-only review-only workspace-write full-access"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l source -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l requires-approval
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l auto-approve
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l approve
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l auto-start
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l no-auto-start
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l provider -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l model -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l routing-mode -r -a "manual quality speed cheap private"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l timezone -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l execution-mode -r -a "worktree local"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l reasoning-effort -r -a "low medium high"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l pinned-context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l context-budget-tokens -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l wait
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l wait-timeout-seconds -r
complete -c poor-cli -n "__fish_seen_subcommand_from task create" -l json

# automation create
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l name -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l prompt -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l every-minutes -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l daily -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l weekly -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l preset -r -a "read-only review-only workspace-write full-access"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l requires-approval
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l auto-approve
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l disabled
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l provider -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l model -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l routing-mode -r -a "manual quality speed cheap private"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l timezone -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l execution-mode -r -a "worktree local"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l reasoning-effort -r -a "low medium high"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l pinned-context-file -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l context-budget-tokens -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l run-now
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l wait
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l wait-timeout-seconds -r
complete -c poor-cli -n "__fish_seen_subcommand_from automation create" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from automation migrate" -l dry-run
complete -c poor-cli -n "__fish_seen_subcommand_from automation migrate" -l force
complete -c poor-cli -n "__fish_seen_subcommand_from automation migrate" -l restore
complete -c poor-cli -n "__fish_seen_subcommand_from automation migrate" -l json

# server
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l stdio
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l host
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l bind -r
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l port -r
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l room -r
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l permission-mode -r -a "prompt auto-safe danger-full-access"
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l ngrok
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l bridge
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l invite -r
complete -c poor-cli -n "__fish_seen_subcommand_from server" -l verbose

# telegram
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l token -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l allowed-users -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l sandbox-preset -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l max-sessions -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l edit-interval -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l webhook-url -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l webhook-port -r
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l verbose
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -s v
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l debug
complete -c poor-cli -n "__fish_seen_subcommand_from telegram" -l log-file -r -a "(__fish_complete_path)"

# Utility command options
complete -c poor-cli -n "__fish_seen_subcommand_from watch" -l debounce -r
complete -c poor-cli -n "__fish_seen_subcommand_from watch" -l scan
complete -c poor-cli -n "__fish_seen_subcommand_from deploy" -l target -s t -r -a "vercel netlify fly railway cloudflare"
complete -c poor-cli -n "__fish_seen_subcommand_from deploy" -l prod
complete -c poor-cli -n "__fish_seen_subcommand_from deploy" -l list
complete -c poor-cli -n "__fish_seen_subcommand_from deploy" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from preview" -l port -r
complete -c poor-cli -n "__fish_seen_subcommand_from preview" -l stop
complete -c poor-cli -n "__fish_seen_subcommand_from review-pr" -l post
complete -c poor-cli -n "__fish_seen_subcommand_from review-pr" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from review-pr" -l ci

# New subcommand options
complete -c poor-cli -n "__fish_seen_subcommand_from checkpoint" -l limit -r
complete -c poor-cli -n "__fish_seen_subcommand_from checkpoint" -l description -s d -r
complete -c poor-cli -n "__fish_seen_subcommand_from checkpoint" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from history" -l limit -r
complete -c poor-cli -n "__fish_seen_subcommand_from history" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from history" -l output -s o -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from session" -l limit -r
complete -c poor-cli -n "__fish_seen_subcommand_from session" -l label -r
complete -c poor-cli -n "__fish_seen_subcommand_from session" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l name -r
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l type -r
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l description -r
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l content -r
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l limit -r
complete -c poor-cli -n "__fish_seen_subcommand_from memory" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from config" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from profile" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from trust" -l path -r -a "(__fish_complete_directories)"
complete -c poor-cli -n "__fish_seen_subcommand_from trust" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from provider" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from provider" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from doctor" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from doctor" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from status" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from status" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from policy" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from policy" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from tools" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from tools" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from mcp" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from mcp" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from cost" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from cost" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l from -r
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l since -r
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l to -r
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l until -r
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l out -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l output -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from audit" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from search" -l mode -r -a "semantic hybrid"
complete -c poor-cli -n "__fish_seen_subcommand_from search" -l limit -r
complete -c poor-cli -n "__fish_seen_subcommand_from search" -l json
complete -c poor-cli -n "__fish_seen_subcommand_from review" -l output-format -r -a "text json"
complete -c poor-cli -n "__fish_seen_subcommand_from review" -l config -r -a "(__fish_complete_path)"
complete -c poor-cli -n "__fish_seen_subcommand_from commit" -l output-format -r -a "text json"
complete -c poor-cli -n "__fish_seen_subcommand_from commit" -l config -r -a "(__fish_complete_path)"

# Mirror to legacy alias if present
complete -c poor-cli-sync -w poor-cli
