//! GPU rendering context using wgpu.

use thiserror::Error;
use tracing::{debug, info};

/// Errors from GPU operations.
#[derive(Debug, Error)]
pub enum GpuError {
    /// No suitable GPU adapter found.
    #[error("no suitable GPU adapter found")]
    NoAdapter,
    /// Failed to request a device.
    #[error("failed to request device: {0}")]
    DeviceRequest(String),
    /// Surface configuration error.
    #[error("surface error: {0}")]
    Surface(String),
}

/// GPU rendering context holding wgpu device, queue, and surface.
pub struct GpuContext {
    /// The wgpu device.
    pub device: wgpu::Device,
    /// The command queue.
    pub queue: wgpu::Queue,
    /// Surface configuration.
    surface_config: wgpu::SurfaceConfiguration,
    /// Surface format.
    pub format: wgpu::TextureFormat,
    /// Adapter metadata for diagnostics.
    adapter_info: wgpu::AdapterInfo,
}

/// Return the preferred wgpu instance settings for the current platform.
pub fn native_instance_descriptor() -> wgpu::InstanceDescriptor {
    wgpu::InstanceDescriptor {
        backends: preferred_backends(),
        ..Default::default()
    }
    .with_env()
}

impl GpuContext {
    /// Create a new GPU context for the given window surface.
    ///
    /// # Errors
    ///
    /// Returns [`GpuError`] if no adapter is found or device creation fails.
    pub async fn new_async(
        instance: &wgpu::Instance,
        surface: &wgpu::Surface<'_>,
        width: u32,
        height: u32,
    ) -> Result<Self, GpuError> {
        let adapter = instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::HighPerformance,
                compatible_surface: Some(surface),
                force_fallback_adapter: false,
            })
            .await
            .ok_or(GpuError::NoAdapter)?;

        let adapter_info = adapter.get_info();
        info!(
            name = %adapter_info.name,
            backend = ?adapter_info.backend,
            device_type = ?adapter_info.device_type,
            "GPU adapter selected"
        );

        let (device, queue) = adapter
            .request_device(&wgpu::DeviceDescriptor::default(), None)
            .await
            .map_err(|e| GpuError::DeviceRequest(e.to_string()))?;

        let capabilities = surface.get_capabilities(&adapter);
        let format = capabilities
            .formats
            .first()
            .copied()
            .unwrap_or(wgpu::TextureFormat::Bgra8UnormSrgb);

        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,
            width: width.max(1),
            height: height.max(1),
            present_mode: wgpu::PresentMode::Fifo,
            alpha_mode: capabilities
                .alpha_modes
                .first()
                .copied()
                .unwrap_or(wgpu::CompositeAlphaMode::Auto),
            view_formats: vec![],
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);

        debug!("GPU context initialized");
        Ok(Self {
            device,
            queue,
            surface_config: config,
            format,
            adapter_info,
        })
    }

    /// Resize the rendering surface.
    pub fn resize(&mut self, surface: &wgpu::Surface<'_>, width: u32, height: u32) {
        self.surface_config.width = width.max(1);
        self.surface_config.height = height.max(1);
        surface.configure(&self.device, &self.surface_config);
    }

    /// Get the current surface dimensions.
    pub fn dimensions(&self) -> (u32, u32) {
        (self.surface_config.width, self.surface_config.height)
    }

    /// Return adapter metadata captured during initialization.
    pub fn adapter_info(&self) -> &wgpu::AdapterInfo {
        &self.adapter_info
    }
}

#[cfg(target_os = "macos")]
fn preferred_backends() -> wgpu::Backends {
    wgpu::Backends::METAL
}

#[cfg(not(target_os = "macos"))]
fn preferred_backends() -> wgpu::Backends {
    wgpu::Backends::all()
}
