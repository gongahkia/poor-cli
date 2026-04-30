//! Minimal entity-handle UI core — distilled from the warpui_core pattern.
//!
//! Pieces:
//!   - [`App`] — owns a typed arena keyed by [`EntityId`].
//!   - [`Entity<T>`] — opaque typed handle (compile-time T witness).
//!   - [`Handle<T>`] — cheap-clone refcounted handle returned to callers.
//!   - [`Context`] — scoped accessor for `App` mutating one entity at a time.
//!   - [`Action`] — caller-defined trait; entities receive actions via
//!     `App::dispatch` and can emit follow-up actions via [`Context::emit`].
//!   - [`View`] — produces an [`Element`] tree (string-typed; downstream
//!     renderers map elements to their primitive set).
//!
//! Out of scope (deliberately): wgpu pipeline, scene graph, text layout,
//! clipboard, keymap. Those stay in their existing crates so this skeleton
//! does not pull in heavy deps.
//!
//! Pure: no I/O, no threading. Single-threaded `Rc`/`RefCell` interior. Tests
//! cover the lifecycle (insert → handle → mutate → drop) and dispatch flow.

#![deny(missing_docs)]
#![forbid(unsafe_code)]

use std::any::Any;
use std::cell::RefCell;
use std::collections::HashMap;
use std::marker::PhantomData;
use std::rc::Rc;

/// Opaque entity identifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct EntityId(u64);

impl EntityId {
    /// Underlying numeric id (escape hatch for diagnostics).
    pub fn raw(self) -> u64 {
        self.0
    }
}

/// Typed entity handle (compile-time witness for `T`).
pub struct Entity<T> {
    id: EntityId,
    _marker: PhantomData<T>,
}

impl<T> std::fmt::Debug for Entity<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Entity").field("id", &self.id).finish()
    }
}

impl<T> Clone for Entity<T> {
    fn clone(&self) -> Self {
        Self {
            id: self.id,
            _marker: PhantomData,
        }
    }
}

impl<T> Copy for Entity<T> {}

impl<T> PartialEq for Entity<T> {
    fn eq(&self, other: &Self) -> bool {
        self.id == other.id
    }
}

impl<T> Eq for Entity<T> {}

impl<T> Entity<T> {
    /// Underlying id.
    pub fn id(&self) -> EntityId {
        self.id
    }
}

/// Cheap-clone refcounted handle. Callers hold `Handle<T>` instead of owning
/// the value directly so the arena can reclaim entries on drop.
pub struct Handle<T: 'static> {
    entity: Entity<T>,
    inner: Rc<RefCell<dyn Any>>,
}

impl<T: 'static> Clone for Handle<T> {
    fn clone(&self) -> Self {
        Self {
            entity: self.entity,
            inner: Rc::clone(&self.inner),
        }
    }
}

impl<T: 'static> Handle<T> {
    /// Entity id.
    pub fn entity(&self) -> Entity<T> {
        self.entity
    }

    /// Borrow the inner value immutably.
    pub fn read<R>(&self, f: impl FnOnce(&T) -> R) -> R {
        let cell = self.inner.borrow();
        let value = cell
            .downcast_ref::<T>()
            .expect("handle type witness violated");
        f(value)
    }

    /// Borrow the inner value mutably.
    pub fn write<R>(&self, f: impl FnOnce(&mut T) -> R) -> R {
        let mut cell = self.inner.borrow_mut();
        let value = cell
            .downcast_mut::<T>()
            .expect("handle type witness violated");
        f(value)
    }

    /// Strong reference count for this handle's storage cell.
    pub fn ref_count(&self) -> usize {
        Rc::strong_count(&self.inner)
    }
}

/// Caller-defined action.
pub trait Action: 'static {}

/// Scoped accessor passed to entity action handlers.
pub struct Context<'a> {
    app: &'a mut App,
    pending: Vec<Box<dyn Action>>,
}

impl<'a> Context<'a> {
    /// Spawn a new entity.
    pub fn new_entity<T: 'static>(&mut self, value: T) -> Handle<T> {
        self.app.new_entity(value)
    }

    /// Resolve an existing entity by handle (clones the rc).
    pub fn handle<T: 'static>(&self, entity: Entity<T>) -> Option<Handle<T>> {
        self.app.handle(entity)
    }

    /// Queue a follow-up action; the runtime delivers it after the current
    /// dispatch returns.
    pub fn emit<A: Action>(&mut self, action: A) {
        self.pending.push(Box::new(action));
    }

    /// Number of follow-up actions queued so far (test diagnostic).
    pub fn pending_len(&self) -> usize {
        self.pending.len()
    }
}

/// Tree-shaped UI element. Downstream renderers map this to their primitives.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Element {
    /// Plain text leaf.
    Text(String),
    /// Container with children.
    Container {
        /// Element tag (`"row"`, `"col"`, `"pane"`, …).
        tag: &'static str,
        /// Children.
        children: Vec<Element>,
    },
}

impl Element {
    /// Build a text leaf.
    pub fn text(s: impl Into<String>) -> Self {
        Self::Text(s.into())
    }

    /// Build a container.
    pub fn container(tag: &'static str, children: Vec<Element>) -> Self {
        Self::Container { tag, children }
    }
}

/// Render trait — entities producing UI implement this.
pub trait View {
    /// Render a snapshot of `self` into an [`Element`] tree.
    fn render(&self) -> Element;
}

/// Per-entity slot.
struct Slot {
    /// `Rc<RefCell<dyn Any>>` — the stored value, type-erased.
    cell: Rc<RefCell<dyn Any>>,
}

/// Application root. Owns the entity arena.
pub struct App {
    next_id: u64,
    slots: HashMap<EntityId, Slot>,
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}

impl App {
    /// New empty app.
    pub fn new() -> Self {
        Self {
            next_id: 1,
            slots: HashMap::new(),
        }
    }

    /// Insert a value, return a [`Handle`] for it.
    pub fn new_entity<T: 'static>(&mut self, value: T) -> Handle<T> {
        let id = EntityId(self.next_id);
        self.next_id += 1;
        let cell: Rc<RefCell<dyn Any>> = Rc::new(RefCell::new(value));
        self.slots.insert(id, Slot { cell: Rc::clone(&cell) });
        Handle {
            entity: Entity {
                id,
                _marker: PhantomData,
            },
            inner: cell,
        }
    }

    /// Resolve an entity to a fresh handle (cloning the rc) if alive.
    pub fn handle<T: 'static>(&self, entity: Entity<T>) -> Option<Handle<T>> {
        let slot = self.slots.get(&entity.id)?;
        Some(Handle {
            entity,
            inner: Rc::clone(&slot.cell),
        })
    }

    /// Drop an entity from the arena. Outstanding handles keep the value
    /// alive until they are dropped, but new lookups via [`App::handle`]
    /// will return `None`.
    pub fn drop_entity<T: 'static>(&mut self, entity: Entity<T>) {
        self.slots.remove(&entity.id);
    }

    /// Number of live entries in the arena.
    pub fn len(&self) -> usize {
        self.slots.len()
    }

    /// Whether the arena is empty.
    pub fn is_empty(&self) -> bool {
        self.slots.is_empty()
    }

    /// Dispatch an action: resolves `entity`, calls `f` with a [`Context`]
    /// scope and a `&mut T` borrow of the entity. Returns the actions queued
    /// via `Context::emit` so the caller can pump them.
    pub fn dispatch<T: 'static, F>(&mut self, entity: Entity<T>, f: F) -> Vec<Box<dyn Action>>
    where
        F: FnOnce(&mut T, &mut Context),
    {
        let handle = match self.handle(entity) {
            Some(h) => h,
            None => return Vec::new(),
        };
        let mut ctx = Context {
            app: self,
            pending: Vec::new(),
        };
        handle.write(|value| f(value, &mut ctx));
        ctx.pending
    }

    /// Render an entity that implements [`View`].
    pub fn render<T: View + 'static>(&self, entity: Entity<T>) -> Option<Element> {
        let handle = self.handle(entity)?;
        Some(handle.read(|v| v.render()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Counter {
        n: i32,
    }

    impl View for Counter {
        fn render(&self) -> Element {
            Element::container("counter", vec![Element::text(format!("n={}", self.n))])
        }
    }

    struct Increment;
    impl Action for Increment {}

    #[test]
    fn insert_then_read_and_write() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 0 });
        h.write(|c| c.n = 5);
        assert_eq!(h.read(|c| c.n), 5);
    }

    #[test]
    fn handle_clone_shares_storage() {
        let mut app = App::new();
        let h1 = app.new_entity(Counter { n: 1 });
        let h2 = h1.clone();
        h1.write(|c| c.n = 9);
        assert_eq!(h2.read(|c| c.n), 9);
        assert!(h1.ref_count() >= 2);
    }

    #[test]
    fn drop_entity_invalidates_lookup_but_keeps_handles() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 7 });
        let entity = h.entity();
        app.drop_entity(entity);
        assert!(app.handle::<Counter>(entity).is_none());
        // outstanding handle still works
        assert_eq!(h.read(|c| c.n), 7);
        assert_eq!(app.len(), 0);
    }

    #[test]
    fn dispatch_runs_handler_and_returns_emits() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 0 });
        let entity = h.entity();
        let pending = app.dispatch(entity, |c, ctx| {
            c.n += 1;
            ctx.emit(Increment);
            ctx.emit(Increment);
        });
        assert_eq!(h.read(|c| c.n), 1);
        assert_eq!(pending.len(), 2);
    }

    #[test]
    fn dispatch_on_dropped_entity_is_noop() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 0 });
        let entity = h.entity();
        app.drop_entity(entity);
        let pending = app.dispatch(entity, |c, _| c.n = 99);
        assert!(pending.is_empty());
    }

    #[test]
    fn render_produces_element_tree() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 3 });
        let el = app.render(h.entity()).expect("render");
        match el {
            Element::Container { tag, children } => {
                assert_eq!(tag, "counter");
                assert_eq!(children.len(), 1);
                assert_eq!(children[0], Element::Text("n=3".into()));
            }
            _ => panic!("expected container"),
        }
    }

    #[test]
    fn arena_ids_are_unique_and_monotonic() {
        let mut app = App::new();
        let a = app.new_entity(Counter { n: 0 });
        let b = app.new_entity(Counter { n: 0 });
        assert_ne!(a.entity().id(), b.entity().id());
        assert!(b.entity().id().raw() > a.entity().id().raw());
    }

    #[test]
    fn entity_clone_and_eq() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 0 });
        let e = h.entity();
        let e2 = e;
        assert_eq!(e, e2);
    }

    #[test]
    fn context_new_entity_inside_dispatch() {
        let mut app = App::new();
        let h = app.new_entity(Counter { n: 0 });
        let entity = h.entity();
        app.dispatch(entity, |_, ctx| {
            let _child = ctx.new_entity(Counter { n: 42 });
        });
        assert_eq!(app.len(), 2);
    }
}
