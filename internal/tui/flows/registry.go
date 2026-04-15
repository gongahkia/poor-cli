package flows

import (
	"context"
	"errors"

	tea "github.com/charmbracelet/bubbletea"
)

type Flow interface {
	Name() string
	Stop() error
	Update(msg tea.Msg) tea.Cmd
}

type LifecycleFlow interface {
	Flow
	StartFlow(ctx context.Context, deps Deps) error
}

type Registry struct {
	flows []Flow
}

func NewRegistry() *Registry {
	return &Registry{}
}

func (r *Registry) Register(f Flow) {
	if r == nil || f == nil {
		return
	}
	r.flows = append(r.flows, f)
}

func (r *Registry) StartAll(ctx context.Context, d Deps) error {
	if r == nil {
		return nil
	}
	var errs []error
	for _, f := range r.flows {
		if lf, ok := f.(LifecycleFlow); ok {
			if err := lf.StartFlow(ctx, d); err != nil {
				errs = append(errs, err)
			}
		}
	}
	return errors.Join(errs...)
}

func (r *Registry) StopAll() error {
	if r == nil {
		return nil
	}
	var errs []error
	for i := len(r.flows) - 1; i >= 0; i-- {
		if err := r.flows[i].Stop(); err != nil {
			errs = append(errs, err)
		}
	}
	return errors.Join(errs...)
}

func (r *Registry) UpdateAll(msg tea.Msg) []tea.Cmd {
	if r == nil {
		return nil
	}
	cmds := make([]tea.Cmd, 0, len(r.flows))
	for _, f := range r.flows {
		if cmd := f.Update(msg); cmd != nil {
			cmds = append(cmds, cmd)
		}
	}
	return cmds
}
