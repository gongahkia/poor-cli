//! Typed runtime effects produced by user actions and plugins.

/// A batch of typed runtime effects emitted while handling an action.
#[derive(Debug, Clone, Default)]
pub struct ActionEffects {
    /// Ordered effects to apply in the runtime.
    pub effects: Vec<RuntimeEffect>,
}

impl ActionEffects {
    /// Create an empty effect batch.
    pub fn new() -> Self {
        Self::default()
    }

    /// Append a runtime effect.
    pub fn push(&mut self, effect: RuntimeEffect) {
        self.effects.push(effect);
    }

    /// Return whether the batch contains no effects.
    pub fn is_empty(&self) -> bool {
        self.effects.is_empty()
    }
}

/// A typed runtime effect that must be applied by the top-level runtime.
#[derive(Debug, Clone, PartialEq)]
pub enum RuntimeEffect {
    /// Write raw bytes to the active pane PTY.
    PtyWrite(Vec<u8>),
    /// Perform a clipboard operation.
    Clipboard(ClipboardEffect),
    /// Perform a viewport operation.
    Viewport(ViewportEffect),
    /// Perform a workspace-level operation.
    Workspace(WorkspaceEffect),
    /// Show or hide one of the runtime overlays.
    Overlay(OverlayEffect),
    /// Apply a zoom level to the renderer.
    Zoom(f32),
}

/// Clipboard work requested by an action or plugin.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClipboardEffect {
    /// Copy the current mouse selection.
    CopySelection,
    /// Copy the currently selected block.
    CopySelectedBlock,
    /// Paste clipboard contents into the active input target.
    Paste,
}

/// Viewport work requested by an action or plugin.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViewportEffect {
    /// Scroll by a number of rows. Positive values move up into scrollback.
    ScrollLines(i32),
    /// Scroll by a number of pages. Positive values move up into scrollback.
    ScrollPages(i32),
    /// Jump to the oldest available scrollback row.
    ScrollToTop,
    /// Jump to the live output position.
    ScrollToBottom,
    /// Enable or disable follow-output behavior.
    FollowOutput(bool),
}

/// Workspace-level work requested by an action or plugin.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorkspaceEffect {
    /// Create a new top-level tab.
    NewTab,
    /// Close the active top-level tab.
    CloseTab,
    /// Focus the next tab.
    NextTab,
    /// Focus the previous tab.
    PrevTab,
    /// Focus a specific tab index (1-based).
    SwitchToTab(u8),
    /// Split the focused pane vertically.
    SplitVertical,
    /// Split the focused pane horizontally.
    SplitHorizontal,
    /// Close the focused split pane.
    CloseSplit,
    /// Focus the pane to the left.
    FocusLeft,
    /// Focus the pane to the right.
    FocusRight,
    /// Focus the pane above.
    FocusUp,
    /// Focus the pane below.
    FocusDown,
    /// Resize the focused split to the left.
    ResizeSplitLeft,
    /// Resize the focused split to the right.
    ResizeSplitRight,
    /// Resize the focused split upward.
    ResizeSplitUp,
    /// Resize the focused split downward.
    ResizeSplitDown,
    /// Save a named workspace snapshot.
    SaveSession(String),
    /// Load a named workspace snapshot.
    LoadSession(String),
}

/// Overlay work requested by an action or plugin.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverlayEffect {
    /// Open the workspace search overlay.
    OpenSearch,
    /// Close the workspace search overlay.
    CloseSearch,
    /// Open the command palette overlay.
    OpenCommandPalette,
    /// Close the command palette overlay.
    CloseCommandPalette,
}
