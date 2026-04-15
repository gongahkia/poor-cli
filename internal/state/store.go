package state

import (
	"context"
	"sync"
)

const subscriberBuffer = MaxMessages

type Store struct {
	mu      sync.RWMutex
	state   AppState
	actions chan dispatchedAction
	subs    map[chan AppState]struct{}
	quit    chan struct{}
	done    chan struct{}
	once    sync.Once
}

type dispatchedAction struct {
	action Action
	done   chan struct{}
}

func NewStore() *Store {
	return NewStoreWithState(AppState{Connection: ConnState{Phase: Disconnected}})
}

func NewStoreWithState(initial AppState) *Store {
	s := &Store{
		state:   cloneAppState(initial),
		actions: make(chan dispatchedAction, MaxMessages),
		subs:    make(map[chan AppState]struct{}),
		quit:    make(chan struct{}),
		done:    make(chan struct{}),
	}
	go s.loop()
	return s
}

func (s *Store) Snapshot() AppState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneAppState(s.state)
}

func (s *Store) Dispatch(action Action) {
	done := make(chan struct{})
	req := dispatchedAction{action: action, done: done}
	select {
	case s.actions <- req:
	case <-s.quit:
		return
	case <-s.done:
		return
	}
	select {
	case <-done:
	case <-s.quit:
	case <-s.done:
	}
}

func (s *Store) Subscribe() (<-chan AppState, func()) {
	ch := make(chan AppState, subscriberBuffer)
	s.mu.Lock()
	s.subs[ch] = struct{}{}
	s.mu.Unlock()
	var once sync.Once
	unsubscribe := func() {
		once.Do(func() {
			s.mu.Lock()
			if _, ok := s.subs[ch]; ok {
				delete(s.subs, ch)
				close(ch)
			}
			s.mu.Unlock()
		})
	}
	return ch, unsubscribe
}

func (s *Store) Run(ctx context.Context) error {
	select {
	case <-ctx.Done():
		s.Close()
		return ctx.Err()
	case <-s.done:
		return nil
	}
}

func (s *Store) Close() {
	s.once.Do(func() {
		close(s.quit)
		<-s.done
	})
}

func (s *Store) loop() {
	defer close(s.done)
	for {
		select {
		case req := <-s.actions:
			s.apply(req)
		case <-s.quit:
			s.closeSubscribers()
			return
		}
	}
}

func (s *Store) apply(req dispatchedAction) {
	s.mu.Lock()
	s.state = Reduce(s.state, req.action)
	snapshot := cloneAppState(s.state)
	for ch := range s.subs {
		ch <- cloneAppState(snapshot)
	}
	s.mu.Unlock()
	close(req.done)
}

func (s *Store) closeSubscribers() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for ch := range s.subs {
		close(ch)
		delete(s.subs, ch)
	}
}
