package server

import (
	"context"
	"time"
)

type HealthStatus int

const (
	HealthUnknown HealthStatus = iota
	HealthHealthy
	HealthUnhealthy
)

type ProbeFunc func(context.Context) error

func (m *Manager) Health() HealthStatus {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.health
}

func (m *Manager) StartHealthProbe(ctx context.Context, interval time.Duration, probe ProbeFunc) {
	if interval <= 0 {
		interval = time.Minute
	}
	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		failures := 0
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if probe == nil {
					continue
				}
				if err := probe(ctx); err != nil {
					failures++
				} else {
					failures = 0
					m.setHealth(HealthHealthy)
				}
				if failures >= 3 {
					m.setHealth(HealthUnhealthy)
				}
			}
		}
	}()
}

func (m *Manager) setHealth(status HealthStatus) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.health = status
}
