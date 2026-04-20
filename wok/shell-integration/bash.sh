#!/bin/bash
# Wok terminal shell integration for Bash
# Emits OSC 133 markers for block detection

__wok_prompt_command() {
    local exit_code=$?
    printf '\033]133;D;%d\007' "$exit_code"
    printf '\033]133;A\007'
    printf '\033]7;file://%s%s\007' "$(hostname)" "$(pwd)"
}

__wok_preexec() {
    printf '\033]133;E;%s\007' "$BASH_COMMAND"
    printf '\033]133;B\007'
    printf '\033]133;C\007'
}

PROMPT_COMMAND="__wok_prompt_command${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
trap '__wok_preexec' DEBUG
printf '\033]133;A\007'
