package widgets

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/gongahkia/gocli-poor/internal/theme"
)

type TopBarDeps struct {
	Theme   *theme.Theme
	Title   string
	Version string
	Cwd     string
}

type TopBar struct {
	theme   theme.Theme
	title   string
	version string
	cwd     string
}

func NewTopBar(d TopBarDeps) *TopBar {
	title := strings.TrimSpace(d.Title)
	if title == "" {
		title = "poor-cli"
	}
	cwd := d.Cwd
	if cwd == "" {
		if wd, err := os.Getwd(); err == nil {
			cwd = wd
		}
	}
	return &TopBar{theme: defaultTheme(d.Theme), title: title, version: strings.TrimSpace(d.Version), cwd: cwd}
}

func (b TopBar) View(width int) string {
	return fitLine(b.theme.Muted.Render(truncateText(b.text(), width)), width)
}

func (b TopBar) text() string {
	title := b.title
	if b.version != "" {
		title += " " + b.version
	}
	crumb := filepath.Base(b.cwd)
	if crumb == "." || crumb == string(filepath.Separator) {
		crumb = b.cwd
	}
	if branch, ok := gitBranch(b.cwd); ok {
		crumb += " · " + branch
	}
	if strings.TrimSpace(crumb) == "" {
		return title
	}
	return title + " · " + crumb
}

func gitBranch(cwd string) (string, bool) {
	for dir := cwd; dir != ""; dir = filepath.Dir(dir) {
		gitPath := filepath.Join(dir, ".git")
		info, err := os.Stat(gitPath)
		if err == nil {
			if info.IsDir() {
				return branchFromGitDir(gitPath)
			}
			return branchFromGitFile(gitPath, dir)
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
	}
	return "", false
}

func branchFromGitFile(path, repoDir string) (string, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", false
	}
	line := strings.TrimSpace(string(data))
	if !strings.HasPrefix(line, "gitdir:") {
		return "", false
	}
	gitDir := strings.TrimSpace(strings.TrimPrefix(line, "gitdir:"))
	if !filepath.IsAbs(gitDir) {
		gitDir = filepath.Join(repoDir, gitDir)
	}
	return branchFromGitDir(gitDir)
}

func branchFromGitDir(gitDir string) (string, bool) {
	data, err := os.ReadFile(filepath.Join(gitDir, "HEAD"))
	if err != nil {
		return "", false
	}
	head := strings.TrimSpace(string(data))
	const prefix = "ref: refs/heads/"
	if strings.HasPrefix(head, prefix) {
		return strings.TrimPrefix(head, prefix), true
	}
	if len(head) >= 7 {
		return head[:7], true
	}
	return head, head != ""
}
