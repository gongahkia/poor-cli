// Package deps pins dependencies consumed across Go client waves.
package deps

import (
	_ "github.com/alecthomas/chroma/v2"
	_ "github.com/charmbracelet/bubbles/textinput"
	_ "github.com/charmbracelet/bubbletea"
	_ "github.com/charmbracelet/lipgloss"
	_ "github.com/mattn/go-runewidth"
	_ "github.com/sahilm/fuzzy"
	_ "github.com/zalando/go-keyring"
	_ "gopkg.in/yaml.v3"
)
