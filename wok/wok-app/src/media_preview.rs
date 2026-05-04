//! macOS-native media preview overlay.
#![allow(unexpected_cfgs)]

use std::path::{Path, PathBuf};

use winit::window::Window;

/// Supported built-in media preview types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MediaKind {
    /// Static image formats handled by AppKit.
    Image,
    /// Animated GIF.
    Gif,
    /// MP4 video.
    Mp4,
}

impl MediaKind {
    /// Human-readable media type.
    pub fn label(self) -> &'static str {
        match self {
            Self::Image => "image",
            Self::Gif => "GIF",
            Self::Mp4 => "MP4",
        }
    }
}

/// Return the supported preview kind for a path.
pub fn media_kind_for_path(path: &Path) -> Option<MediaKind> {
    let extension = path.extension()?.to_str()?.to_ascii_lowercase();
    match extension.as_str() {
        "gif" => Some(MediaKind::Gif),
        "mp4" | "m4v" => Some(MediaKind::Mp4),
        "png" | "jpg" | "jpeg" | "webp" | "bmp" | "tif" | "tiff" | "heic" | "heif" => {
            Some(MediaKind::Image)
        }
        _ => None,
    }
}

/// Native preview instance mounted into the Wok window.
pub struct MediaPreview {
    path: PathBuf,
    kind: MediaKind,
    is_playing: bool,
    platform: PlatformMediaPreview,
}

impl MediaPreview {
    /// Open a new preview inside the given window.
    pub fn open(
        window: &Window,
        path: PathBuf,
        kind: MediaKind,
        frame: PreviewFrame,
    ) -> Result<Self, String> {
        let platform = PlatformMediaPreview::open(window, &path, kind, frame)?;
        Ok(Self {
            path,
            kind,
            is_playing: matches!(kind, MediaKind::Gif | MediaKind::Mp4),
            platform,
        })
    }

    /// Resize the native preview.
    pub fn set_frame(&mut self, frame: PreviewFrame) {
        self.platform.set_frame(frame);
    }

    /// Previewed file path.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Previewed media kind.
    pub fn kind(&self) -> MediaKind {
        self.kind
    }

    /// Toggle playback for animated media. Returns the new playback state.
    pub fn toggle_playback(&mut self) -> Option<bool> {
        if !matches!(self.kind, MediaKind::Gif | MediaKind::Mp4) {
            return None;
        }
        self.is_playing = !self.is_playing;
        self.platform.set_playing(self.kind, self.is_playing);
        Some(self.is_playing)
    }
}

/// AppKit frame in logical window points.
#[derive(Debug, Clone, Copy)]
pub struct PreviewFrame {
    /// Left edge in points.
    pub x: f64,
    /// Bottom edge in points.
    pub y: f64,
    /// Width in points.
    pub width: f64,
    /// Height in points.
    pub height: f64,
}

#[cfg(target_os = "macos")]
mod platform {
    use std::ffi::CString;
    use std::path::Path;
    use std::ptr;

    use objc::runtime::{Object, YES};
    use objc::{class, msg_send, sel, sel_impl};
    use winit::raw_window_handle::{HasWindowHandle, RawWindowHandle};
    use winit::window::Window;

    use super::{MediaKind, PreviewFrame};

    #[link(name = "AppKit", kind = "framework")]
    #[link(name = "AVKit", kind = "framework")]
    #[link(name = "AVFoundation", kind = "framework")]
    extern "C" {}

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct NSPoint {
        x: f64,
        y: f64,
    }

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct NSSize {
        width: f64,
        height: f64,
    }

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct NSRect {
        origin: NSPoint,
        size: NSSize,
    }

    pub(super) struct PlatformMediaPreview {
        container: *mut Object,
        child: *mut Object,
        player: *mut Object,
    }

    impl PlatformMediaPreview {
        pub(super) fn open(
            window: &Window,
            path: &Path,
            kind: MediaKind,
            frame: PreviewFrame,
        ) -> Result<Self, String> {
            let parent = appkit_parent_view(window)?;

            // SAFETY: AppKit and AVKit are touched on Wok's main event-loop
            // thread. Objects created with alloc/init are balanced in Drop.
            unsafe {
                let container = create_container(parent, frame)?;
                let (child, player) = match kind {
                    MediaKind::Image | MediaKind::Gif => {
                        (create_image_view(path, frame)?, ptr::null_mut())
                    }
                    MediaKind::Mp4 => create_video_view(path, frame)?,
                };
                let _: () = msg_send![container, addSubview: child];
                Ok(Self {
                    container,
                    child,
                    player,
                })
            }
        }

        pub(super) fn set_frame(&mut self, frame: PreviewFrame) {
            // SAFETY: Both pointers are owned Objective-C views while self is
            // alive. AppKit frame updates run on the main event-loop thread.
            unsafe {
                let container_frame = ns_rect(frame.x, frame.y, frame.width, frame.height);
                let child_frame = ns_rect(0.0, 0.0, frame.width, frame.height);
                let _: () = msg_send![self.container, setFrame: container_frame];
                let _: () = msg_send![self.child, setFrame: child_frame];
            }
        }

        pub(super) fn set_playing(&mut self, kind: MediaKind, playing: bool) {
            // SAFETY: The Objective-C objects are alive while self is alive and
            // are only touched on the main event-loop thread.
            unsafe {
                match kind {
                    MediaKind::Gif => {
                        let animates = if playing { YES } else { objc::runtime::NO };
                        let _: () = msg_send![self.child, setAnimates: animates];
                    }
                    MediaKind::Mp4 if !self.player.is_null() => {
                        if playing {
                            let _: () = msg_send![self.player, play];
                        } else {
                            let _: () = msg_send![self.player, pause];
                        }
                    }
                    MediaKind::Image | MediaKind::Mp4 => {}
                }
            }
        }
    }

    fn appkit_parent_view(window: &Window) -> Result<*mut Object, String> {
        let handle = window.window_handle().map_err(|error| error.to_string())?;
        match handle.as_raw() {
            RawWindowHandle::AppKit(handle) => Ok(handle.ns_view.as_ptr().cast::<Object>()),
            other => Err(format!("expected AppKit window handle, got {other:?}")),
        }
    }

    impl Drop for PlatformMediaPreview {
        fn drop(&mut self) {
            // SAFETY: These objects were created with alloc/init. Removing from
            // superviews releases AppKit ownership; release balances ours.
            unsafe {
                if !self.child.is_null() {
                    let _: () = msg_send![self.child, removeFromSuperview];
                    let _: () = msg_send![self.child, release];
                    self.child = ptr::null_mut();
                }
                if !self.player.is_null() {
                    let _: () = msg_send![self.player, release];
                    self.player = ptr::null_mut();
                }
                if !self.container.is_null() {
                    let _: () = msg_send![self.container, removeFromSuperview];
                    let _: () = msg_send![self.container, release];
                    self.container = ptr::null_mut();
                }
            }
        }
    }

    unsafe fn create_container(
        parent: *mut Object,
        frame: PreviewFrame,
    ) -> Result<*mut Object, String> {
        let rect = ns_rect(frame.x, frame.y, frame.width, frame.height);
        let view: *mut Object = msg_send![class!(NSView), alloc];
        let view: *mut Object = msg_send![view, initWithFrame: rect];
        if view.is_null() {
            return Err("failed to create preview container".to_string());
        }
        let _: () = msg_send![view, setWantsLayer: YES];
        let layer: *mut Object = msg_send![view, layer];
        if !layer.is_null() {
            let color: *mut Object = msg_send![class!(NSColor), blackColor];
            let cg_color: *mut Object = msg_send![color, CGColor];
            let _: () = msg_send![layer, setBackgroundColor: cg_color];
        }
        let _: () = msg_send![view, setAutoresizingMask: 18usize];
        let _: () = msg_send![parent, addSubview: view];
        Ok(view)
    }

    unsafe fn create_image_view(path: &Path, frame: PreviewFrame) -> Result<*mut Object, String> {
        let path_string = ns_string(path)?;
        let image: *mut Object = msg_send![class!(NSImage), alloc];
        let image: *mut Object = msg_send![image, initWithContentsOfFile: path_string];
        if image.is_null() {
            return Err(format!("failed to load image '{}'", path.display()));
        }

        let rect = ns_rect(0.0, 0.0, frame.width, frame.height);
        let view: *mut Object = msg_send![class!(NSImageView), alloc];
        let view: *mut Object = msg_send![view, initWithFrame: rect];
        if view.is_null() {
            let _: () = msg_send![image, release];
            return Err("failed to create image preview view".to_string());
        }
        let _: () = msg_send![view, setImage: image];
        let _: () = msg_send![view, setAnimates: YES];
        let _: () = msg_send![view, setImageScaling: 3isize];
        let _: () = msg_send![view, setAutoresizingMask: 18usize];
        let _: () = msg_send![image, release];
        Ok(view)
    }

    unsafe fn create_video_view(
        path: &Path,
        frame: PreviewFrame,
    ) -> Result<(*mut Object, *mut Object), String> {
        let path_string = ns_string(path)?;
        let url: *mut Object = msg_send![class!(NSURL), fileURLWithPath: path_string];
        if url.is_null() {
            return Err(format!("failed to create video URL '{}'", path.display()));
        }
        let player: *mut Object = msg_send![class!(AVPlayer), playerWithURL: url];
        if player.is_null() {
            return Err(format!("failed to create MP4 player '{}'", path.display()));
        }
        let _: () = msg_send![player, retain];

        let rect = ns_rect(0.0, 0.0, frame.width, frame.height);
        let view: *mut Object = msg_send![class!(AVPlayerView), alloc];
        let view: *mut Object = msg_send![view, initWithFrame: rect];
        if view.is_null() {
            let _: () = msg_send![player, release];
            return Err("failed to create MP4 preview view".to_string());
        }
        let _: () = msg_send![view, setPlayer: player];
        let _: () = msg_send![view, setControlsStyle: 1isize];
        let _: () = msg_send![view, setAutoresizingMask: 18usize];
        let _: () = msg_send![player, play];
        Ok((view, player))
    }

    unsafe fn ns_string(path: &Path) -> Result<*mut Object, String> {
        let text = path.to_string_lossy();
        let c_string =
            CString::new(text.as_bytes()).map_err(|_| "path contains a NUL byte".to_string())?;
        let string: *mut Object =
            msg_send![class!(NSString), stringWithUTF8String: c_string.as_ptr()];
        if string.is_null() {
            Err("failed to create NSString for path".to_string())
        } else {
            Ok(string)
        }
    }

    fn ns_rect(x: f64, y: f64, width: f64, height: f64) -> NSRect {
        NSRect {
            origin: NSPoint { x, y },
            size: NSSize { width, height },
        }
    }
}

#[cfg(target_os = "macos")]
use platform::PlatformMediaPreview;

#[cfg(not(target_os = "macos"))]
mod platform {
    use std::path::Path;

    use winit::window::Window;

    use super::{MediaKind, PreviewFrame};

    pub(super) struct PlatformMediaPreview;

    impl PlatformMediaPreview {
        pub(super) fn open(
            _window: &Window,
            _path: &Path,
            _kind: MediaKind,
            _frame: PreviewFrame,
        ) -> Result<Self, String> {
            Err("media preview is currently macOS-only".to_string())
        }

        pub(super) fn set_frame(&mut self, _frame: PreviewFrame) {}

        pub(super) fn set_playing(&mut self, _kind: MediaKind, _playing: bool) {}
    }
}

#[cfg(not(target_os = "macos"))]
use platform::PlatformMediaPreview;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_media_kind_for_path() {
        assert_eq!(
            media_kind_for_path(Path::new("screen.PNG")),
            Some(MediaKind::Image)
        );
        assert_eq!(
            media_kind_for_path(Path::new("demo.gif")),
            Some(MediaKind::Gif)
        );
        assert_eq!(
            media_kind_for_path(Path::new("clip.mp4")),
            Some(MediaKind::Mp4)
        );
        assert_eq!(media_kind_for_path(Path::new("notes.txt")), None);
    }
}
