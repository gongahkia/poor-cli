#!/bin/bash
# Installation script for poor-cli shell completions

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing poor-cli shell completions..."
echo

# Detect shell
detect_shell() {
    if [ -n "$BASH_VERSION" ]; then
        echo "bash"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "zsh"
    elif [ -n "$FISH_VERSION" ]; then
        echo "fish"
    else
        # Try to detect from SHELL env var
        case "$SHELL" in
            */bash)
                echo "bash"
                ;;
            */zsh)
                echo "zsh"
                ;;
            */fish)
                echo "fish"
                ;;
            *)
                echo "unknown"
                ;;
        esac
    fi
}

SHELL_TYPE=$(detect_shell)

install_bash() {
    echo "Installing Bash completion..."

    # Check if bash-completion is available
    if [ -d /etc/bash_completion.d ]; then
        echo "  Copying to /etc/bash_completion.d/ (requires sudo)"
        sudo cp "$SCRIPT_DIR/poor-cli.bash" /etc/bash_completion.d/
        echo "  ✓ Installed system-wide"
    elif [ -d ~/.bash_completion.d ]; then
        cp "$SCRIPT_DIR/poor-cli.bash" ~/.bash_completion.d/
        echo "  ✓ Installed to ~/.bash_completion.d/"
    else
        # Create user completion directory
        mkdir -p ~/.bash_completion.d
        cp "$SCRIPT_DIR/poor-cli.bash" ~/.bash_completion.d/

        # Add source line to .bashrc if not present
        if ! grep -q "poor-cli.bash" ~/.bashrc; then
            echo "" >> ~/.bashrc
            echo "# poor-cli completion" >> ~/.bashrc
            echo "source ~/.bash_completion.d/poor-cli.bash" >> ~/.bashrc
            echo "  ✓ Added source line to ~/.bashrc"
        fi
        echo "  ✓ Installed to ~/.bash_completion.d/"
    fi

    echo "  Run 'source ~/.bashrc' or restart your shell to activate"
}

install_zsh() {
    echo "Installing Zsh completion..."

    # Create completion directory if it doesn't exist
    mkdir -p ~/.zsh/completions
    cp "$SCRIPT_DIR/poor-cli.zsh" ~/.zsh/completions/_poor-cli

    # Add fpath to .zshrc if not present
    if ! grep -q "~/.zsh/completions" ~/.zshrc 2>/dev/null; then
        echo "" >> ~/.zshrc
        echo "# poor-cli completion" >> ~/.zshrc
        echo "fpath=(~/.zsh/completions \$fpath)" >> ~/.zshrc
        echo "autoload -Uz compinit && compinit" >> ~/.zshrc
        echo "  ✓ Added fpath to ~/.zshrc"
    fi

    echo "  ✓ Installed to ~/.zsh/completions/"
    echo "  Run 'source ~/.zshrc' or restart your shell to activate"
}

install_fish() {
    echo "Installing Fish completion..."

    # Create fish completion directory if it doesn't exist
    mkdir -p ~/.config/fish/completions
    cp "$SCRIPT_DIR/poor-cli.fish" ~/.config/fish/completions/

    echo "  ✓ Installed to ~/.config/fish/completions/"
    echo "  Completions will be available immediately in new fish sessions"
}

# Main installation
case "$SHELL_TYPE" in
    bash)
        install_bash
        ;;
    zsh)
        install_zsh
        ;;
    fish)
        install_fish
        ;;
    *)
        echo "Could not detect shell type."
        echo "Please choose:"
        echo "  1) Bash"
        echo "  2) Zsh"
        echo "  3) Fish"
        echo "  4) All"
        read -p "Choice: " choice

        case $choice in
            1)
                install_bash
                ;;
            2)
                install_zsh
                ;;
            3)
                install_fish
                ;;
            4)
                install_bash
                install_zsh
                install_fish
                ;;
            *)
                echo "Invalid choice"
                exit 1
                ;;
        esac
        ;;
esac

echo
echo "✓ Installation complete!"
echo
echo "To uninstall, remove the completion files manually:"
echo "  Bash:  rm ~/.bash_completion.d/poor-cli.bash"
echo "  Zsh:   rm ~/.zsh/completions/_poor-cli"
echo "  Fish:  rm ~/.config/fish/completions/poor-cli.fish"
