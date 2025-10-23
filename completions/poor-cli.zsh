#compdef poor-cli poor-cli-sync

# Zsh completion for poor-cli
# Add to ~/.zshrc:
#   fpath=(/path/to/completions $fpath)
#   autoload -Uz compinit && compinit

_poor_cli() {
    local -a commands

    commands=(
        '/help:Show help message'
        '/quit:Exit the REPL'
        '/exit:Exit the REPL'
        '/clear:Clear conversation history'
        '/history:Show recent messages'
        '/sessions:List all sessions'
        '/new-session:Start fresh session'
        '/checkpoints:List all checkpoints'
        '/checkpoint:Create manual checkpoint'
        '/rewind:Restore checkpoint'
        '/diff:Compare two files'
        '/provider:Show provider info'
        '/switch:Switch AI provider'
        '/config:Show configuration'
        '/verbose:Toggle verbose logging'
        '/plan-mode:Toggle plan mode'
    )

    _arguments \
        '1: :->command' \
        '*: :->args'

    case $state in
        command)
            _describe -t commands 'poor-cli commands' commands
            ;;
        args)
            case $words[2] in
                /diff|/rewind)
                    _files
                    ;;
            esac
            ;;
    esac
}

_poor_cli "$@"
