package server

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestHealthProbeTransitions(t *testing.T) {
	m := NewManager(Config{})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	fail := true
	m.StartHealthProbe(ctx, time.Millisecond, func(context.Context) error {
		if fail {
			return errors.New("down")
		}
		return nil
	})
	waitFor(t, time.Second, func() bool { return m.Health() == HealthUnhealthy })
	fail = false
	waitFor(t, time.Second, func() bool { return m.Health() == HealthHealthy })
}
