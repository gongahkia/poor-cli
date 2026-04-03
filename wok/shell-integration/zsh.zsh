#!/bin/zsh
# Walk terminal shell integration for Zsh
# Emits OSC 133 markers for block detection

__walk_precmd() {
    local exit_code=$?
    printf '\033]133;D;%d\007' "$exit_code"
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' "$(hostname)" "$(pwd)"
}

__walk_preexec() {
    printf '\033]133;E;%s\007' "$1"
    printf '\033]133;B\007'
    printf '\033]133;C\007'
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd __walk_precmd
add-zsh-hook preexec __walk_preexec
printf '\033]133;A\007'
