//go:build windows

package server

import (
	"fmt"
	"os/exec"
	"syscall"
)

const createNewProcessGroup = 0x00000200
const ctrlBreakEvent = 1

var generateConsoleCtrlEvent = syscall.NewLazyDLL("kernel32.dll").NewProc("GenerateConsoleCtrlEvent")

func prepareCmd(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNewProcessGroup}
}

func terminateProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	r1, _, err := generateConsoleCtrlEvent.Call(ctrlBreakEvent, uintptr(uint32(cmd.Process.Pid)))
	if r1 != 0 {
		return nil
	}
	if err != syscall.Errno(0) {
		return err
	}
	return fmt.Errorf("GenerateConsoleCtrlEvent failed")
}

func killProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	return cmd.Process.Kill()
}
