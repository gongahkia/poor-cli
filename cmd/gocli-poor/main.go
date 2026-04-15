package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/gongahkia/gocli-poor/internal/config"
	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/rpc"
	"github.com/gongahkia/gocli-poor/internal/server"
	"github.com/gongahkia/gocli-poor/internal/state"
	"github.com/gongahkia/gocli-poor/internal/tui"
)

var (
	Version = "dev"
	Commit  = "none"
)

func main() {
	opts := parseArgs()
	if opts.version {
		fmt.Printf("gocli-poor %s (%s)\n", Version, Commit)
		return
	}

	cfg, err := config.Load()
	if err != nil {
		fail(err)
	}
	if opts.serverPath != "" {
		cfg.ServerPath = opts.serverPath
	}
	appState := &state.AppState{
		Provider: state.ProviderState{Name: cfg.DefaultProvider, Model: cfg.DefaultModel},
		Connection: state.ConnState{
			Phase: state.Disconnected,
		},
		ContextPressure: state.ContextPressure{Budget: cfg.ContextBudgetTokens},
	}
	var tuiOpts []tui.Option
	tuiOpts = append(tuiOpts, tui.WithIntroVersion(Version))
	if !opts.noServer {
		mgr, client, initCmd, err := startManagedServer(cfg, appState)
		if err != nil {
			fail(err)
		}
		defer shutdownManagedServer(mgr, client)
		tuiOpts = append(tuiOpts, tui.WithRPCClient(client))
		if initCmd != nil {
			tuiOpts = append(tuiOpts, tui.WithConnectCmd(initCmd))
		}
	}
	if err := tui.Run(appState, tuiOpts...); err != nil {
		fail(err)
	}
}

type cliOptions struct {
	version    bool
	noServer   bool
	serverPath string
}

func parseArgs() cliOptions {
	var opts cliOptions
	fs := flag.NewFlagSet("gocli-poor", flag.ExitOnError)
	fs.BoolVar(&opts.version, "version", false, "print version")
	fs.BoolVar(&opts.noServer, "no-server", false, "start TUI without launching a backend server")
	fs.StringVar(&opts.serverPath, "server-path", "", "path to poor-cli-server executable")
	fs.Usage = printUsage
	if len(os.Args) > 1 && os.Args[1] == "version" {
		opts.version = true
		return opts
	}
	if len(os.Args) > 1 && os.Args[1] == "help" {
		printUsage()
		os.Exit(0)
	}
	if err := fs.Parse(os.Args[1:]); err != nil {
		fail(err)
	}
	return opts
}

func printUsage() {
	fmt.Println("gocli-poor - TUI chat client for poor-cli")
	fmt.Println("")
	fmt.Println("Usage:")
	fmt.Println("  gocli-poor [--server-path PATH] [--no-server]")
	fmt.Println("  gocli-poor --version")
}

func startManagedServer(cfg *config.Config, appState *state.AppState) (*server.Manager, *rpc.Client, tea.Cmd, error) {
	serverCfg := server.Config{BinaryPath: cfg.ServerPath, Cwd: mustCwd(), ReadyTimeout: 2 * time.Second}
	if cfg.ServerPath == "" {
		serverCfg.BinaryPath, serverCfg.Args = defaultServerCommand()
	} else if filepath.Base(cfg.ServerPath) == "poor-cli" {
		serverCfg.Args = []string{"server"}
	}
	mgr := server.NewManager(serverCfg)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := mgr.Start(ctx); err != nil {
		return nil, nil, nil, err
	}
	client := rpc.NewClient(mgr.Stdout(), mgr.Stdin())
	cmd, err := initializeServer(client, cfg, appState)
	if err != nil {
		shutdownManagedServer(mgr, client)
		return nil, nil, nil, err
	}
	return mgr, client, cmd, nil
}

func initializeServer(client *rpc.Client, cfg *config.Config, appState *state.AppState) (tea.Cmd, error) {
	streaming := true
	params := protocol.InitializeParams{
		Provider:           cfg.DefaultProvider,
		Model:              cfg.DefaultModel,
		Streaming:          &streaming,
		PermissionMode:     "prompt",
		ClientCapabilities: map[string]any{"reviewFlows": map[string]any{"permissionRequests": true}},
	}
	var result protocol.InitializeResult
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	if err := client.Call(ctx, protocol.MethodInitialize, params, &result); err != nil {
		return nil, err
	}
	appState.Connection = state.ConnState{Phase: state.Ready}
	if info := result.Capabilities.ProviderInfo; info != nil {
		appState.Provider = state.ProviderState{Name: info.Name, Model: info.Model, Caps: info.Capabilities}
	}
	if result.Capabilities.NeedsAPIKey {
		msg := result.Capabilities.Message
		provider := cfg.DefaultProvider
		return func() tea.Msg { return tui.InitializeNeedsAPIKeyMsg{Provider: provider, Message: msg} }, nil
	}
	return nil, nil
}

func shutdownManagedServer(mgr *server.Manager, client *rpc.Client) {
	if client != nil {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		_ = client.Call(ctx, protocol.MethodShutdown, nil, nil)
		cancel()
	}
	if mgr != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		_ = mgr.Shutdown(ctx)
		cancel()
	}
	if client != nil {
		_ = client.Close()
	}
}

func defaultServerCommand() (string, []string) {
	if path, err := exec.LookPath("poor-cli-server"); err == nil {
		return path, nil
	}
	if _, err := os.Stat(filepath.Join("poor_cli", "server", "__main__.py")); err == nil {
		if path, err := exec.LookPath("python3"); err == nil {
			return path, []string{"-m", "poor_cli.server"}
		}
	}
	return "", nil
}

func mustCwd() string {
	wd, err := os.Getwd()
	if err != nil {
		return ""
	}
	return wd
}

func fail(err error) {
	fmt.Fprintf(os.Stderr, "gocli-poor: %v\n", err)
	os.Exit(1)
}
