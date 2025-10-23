# Fish completion for poor-cli
# Copy to ~/.config/fish/completions/poor-cli.fish

# Remove old completions
complete -c poor-cli -e
complete -c poor-cli-sync -e

# Session Management
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/help" -d "Show help message"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/quit" -d "Exit the REPL"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/exit" -d "Exit the REPL"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/clear" -d "Clear conversation"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/history" -d "Show recent messages"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/sessions" -d "List all sessions"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/new-session" -d "Start fresh session"

# Checkpoints & Undo
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/checkpoints" -d "List all checkpoints"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/checkpoint" -d "Create manual checkpoint"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/rewind" -d "Restore checkpoint"
complete -c poor-cli -r -n "__fish_seen_subcommand_from /rewind" -d "Checkpoint ID or 'last'"

# Diff command with file completion
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/diff" -d "Compare two files"
complete -c poor-cli -r -n "__fish_seen_subcommand_from /diff" -d "File path"

# Provider Management
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/provider" -d "Show provider info"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/switch" -d "Switch AI provider"

# Configuration
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/config" -d "Show configuration"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/verbose" -d "Toggle verbose logging"
complete -c poor-cli -f -n "__fish_use_subcommand" -a "/plan-mode" -d "Toggle plan mode"

# Copy all completions for poor-cli-sync
complete -c poor-cli-sync -w poor-cli
