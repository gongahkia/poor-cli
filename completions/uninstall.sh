#!/bin/bash
# Uninstall script for poor-cli shell completions

set -e

echo "Uninstalling poor-cli shell completions..."
echo

removed=0

# Bash
for f in /etc/bash_completion.d/poor-cli.bash ~/.bash_completion.d/poor-cli.bash; do
    if [ -f "$f" ]; then
        if [[ "$f" == /etc/* ]]; then
            sudo rm -f "$f" && echo "  Removed $f" && removed=$((removed+1))
        else
            rm -f "$f" && echo "  Removed $f" && removed=$((removed+1))
        fi
    fi
done

# Remove source line from .bashrc
if [ -f ~/.bashrc ] && grep -q "poor-cli.bash" ~/.bashrc; then
    sed -i '/# poor-cli completion/d;/poor-cli\.bash/d' ~/.bashrc
    echo "  Cleaned ~/.bashrc"
fi

# Zsh
if [ -f ~/.zsh/completions/_poor-cli ]; then
    rm -f ~/.zsh/completions/_poor-cli
    echo "  Removed ~/.zsh/completions/_poor-cli"
    removed=$((removed+1))
fi

# Fish
if [ -f ~/.config/fish/completions/poor-cli.fish ]; then
    rm -f ~/.config/fish/completions/poor-cli.fish
    echo "  Removed ~/.config/fish/completions/poor-cli.fish"
    removed=$((removed+1))
fi

echo
if [ "$removed" -eq 0 ]; then
    echo "No completions found to remove."
else
    echo "Removed $removed completion file(s)."
    echo "Restart your shell to apply changes."
fi
