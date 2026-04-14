package server

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"runtime"
)

func ResolveBinary(override string) (string, error) {
	if override != "" {
		return requireExecutable(override, "override")
	}
	if env := os.Getenv("POOR_CLI_SERVER_PATH"); env != "" {
		return requireExecutable(env, "POOR_CLI_SERVER_PATH")
	}
	if path, err := exec.LookPath("poor-cli-server"); err == nil {
		return path, nil
	}
	if path, err := exec.LookPath("poor-cli"); err == nil {
		return path, nil
	}
	return "", errors.New("server: poor-cli-server not found; install poor-cli-server or set POOR_CLI_SERVER_PATH to an executable path")
}

func requireExecutable(path, source string) (string, error) {
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("server: %s %q is not usable: %w", source, path, err)
	}
	if info.IsDir() {
		return "", fmt.Errorf("server: %s %q is a directory", source, path)
	}
	if runtime.GOOS != "windows" && info.Mode()&0111 == 0 {
		return "", fmt.Errorf("server: %s %q is not executable", source, path)
	}
	return path, nil
}
