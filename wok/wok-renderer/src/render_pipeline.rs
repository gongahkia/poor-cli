//! Render pipeline: wgpu pipeline for drawing terminal grid cells.

use wgpu::util::DeviceExt;

use crate::gpu::GpuContext;
use crate::pipeline::{QuadBatch, Vertex};

const UPLOAD_FRAME_COUNT: usize = 3;

/// Uniform data passed to the shader.
#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Uniforms {
    screen_size: [f32; 2],
    _padding: [f32; 2],
}

/// The GPU render pipeline for terminal rendering.
pub struct TerminalRenderPipeline {
    pipeline: wgpu::RenderPipeline,
    bind_group_layout: wgpu::BindGroupLayout,
    bind_group: wgpu::BindGroup,
    uniform_buffer: wgpu::Buffer,
    atlas_texture: wgpu::Texture,
    atlas_view: wgpu::TextureView,
    sampler: wgpu::Sampler,
    background_texture: wgpu::Texture,
    background_view: wgpu::TextureView,
    upload_frames: Vec<UploadFrame>,
    upload_frame_index: usize,
}

struct UploadFrame {
    vertex_buffer: Option<wgpu::Buffer>,
    index_buffer: Option<wgpu::Buffer>,
    vertex_buffer_capacity: u64,
    index_buffer_capacity: u64,
}

impl UploadFrame {
    fn new() -> Self {
        Self {
            vertex_buffer: None,
            index_buffer: None,
            vertex_buffer_capacity: 0,
            index_buffer_capacity: 0,
        }
    }

    fn ensure_buffers(
        &mut self,
        gpu: &GpuContext,
        vertex_bytes_needed: u64,
        index_bytes_needed: u64,
    ) {
        if self.vertex_buffer_capacity < vertex_bytes_needed {
            self.vertex_buffer_capacity = grow_buffer_capacity(vertex_bytes_needed);
            self.vertex_buffer = Some(gpu.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("vertex_buffer"),
                size: self.vertex_buffer_capacity,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }));
        }

        if self.index_buffer_capacity < index_bytes_needed {
            self.index_buffer_capacity = grow_buffer_capacity(index_bytes_needed);
            self.index_buffer = Some(gpu.device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("index_buffer"),
                size: self.index_buffer_capacity,
                usage: wgpu::BufferUsages::INDEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }));
        }
    }
}

impl TerminalRenderPipeline {
    /// Create a new terminal render pipeline.
    pub fn new(gpu: &GpuContext) -> Self {
        let shader = gpu
            .device
            .create_shader_module(wgpu::ShaderModuleDescriptor {
                label: Some("terminal_shader"),
                source: wgpu::ShaderSource::Wgsl(include_str!("terminal.wgsl").into()),
            });

        // Create a 1x1 white atlas texture as placeholder
        let atlas_texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
            label: Some("glyph_atlas"),
            size: wgpu::Extent3d {
                width: 2_048,
                height: 2_048,
                depth_or_array_layers: 1,
            },
            mip_level_count: 1,
            sample_count: 1,
            dimension: wgpu::TextureDimension::D2,
            format: wgpu::TextureFormat::R8Unorm,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
            view_formats: &[],
        });

        // Write a white pixel at (0,0) so glyph quads have something to sample
        gpu.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &atlas_texture,
                mip_level: 0,
                origin: wgpu::Origin3d::ZERO,
                aspect: wgpu::TextureAspect::All,
            },
            &[255u8],
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(2_048),
                rows_per_image: Some(2_048),
            },
            wgpu::Extent3d {
                width: 1,
                height: 1,
                depth_or_array_layers: 1,
            },
        );

        let atlas_view = atlas_texture.create_view(&wgpu::TextureViewDescriptor::default());
        let (background_texture, background_view) = create_background_texture(gpu, None);

        let sampler = gpu.device.create_sampler(&wgpu::SamplerDescriptor {
            address_mode_u: wgpu::AddressMode::ClampToEdge,
            address_mode_v: wgpu::AddressMode::ClampToEdge,
            mag_filter: wgpu::FilterMode::Linear,
            min_filter: wgpu::FilterMode::Linear,
            ..Default::default()
        });

        let uniform_buffer = gpu
            .device
            .create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some("uniforms"),
                contents: bytemuck::cast_slice(&[Uniforms {
                    screen_size: [800.0, 600.0],
                    _padding: [0.0; 2],
                }]),
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
            });

        let bind_group_layout =
            gpu.device
                .create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
                    label: Some("terminal_bind_group_layout"),
                    entries: &[
                        wgpu::BindGroupLayoutEntry {
                            binding: 0,
                            visibility: wgpu::ShaderStages::VERTEX,
                            ty: wgpu::BindingType::Buffer {
                                ty: wgpu::BufferBindingType::Uniform,
                                has_dynamic_offset: false,
                                min_binding_size: None,
                            },
                            count: None,
                        },
                        wgpu::BindGroupLayoutEntry {
                            binding: 1,
                            visibility: wgpu::ShaderStages::FRAGMENT,
                            ty: wgpu::BindingType::Texture {
                                sample_type: wgpu::TextureSampleType::Float { filterable: true },
                                view_dimension: wgpu::TextureViewDimension::D2,
                                multisampled: false,
                            },
                            count: None,
                        },
                        wgpu::BindGroupLayoutEntry {
                            binding: 2,
                            visibility: wgpu::ShaderStages::FRAGMENT,
                            ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                            count: None,
                        },
                        wgpu::BindGroupLayoutEntry {
                            binding: 3,
                            visibility: wgpu::ShaderStages::FRAGMENT,
                            ty: wgpu::BindingType::Texture {
                                sample_type: wgpu::TextureSampleType::Float { filterable: true },
                                view_dimension: wgpu::TextureViewDimension::D2,
                                multisampled: false,
                            },
                            count: None,
                        },
                        wgpu::BindGroupLayoutEntry {
                            binding: 4,
                            visibility: wgpu::ShaderStages::FRAGMENT,
                            ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering),
                            count: None,
                        },
                    ],
                });

        let bind_group = create_bind_group(
            gpu,
            &bind_group_layout,
            &uniform_buffer,
            &atlas_view,
            &background_view,
            &sampler,
        );

        let pipeline_layout = gpu
            .device
            .create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
                label: Some("terminal_pipeline_layout"),
                bind_group_layouts: &[&bind_group_layout],
                push_constant_ranges: &[],
            });

        let pipeline = gpu
            .device
            .create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some("terminal_pipeline"),
                layout: Some(&pipeline_layout),
                vertex: wgpu::VertexState {
                    module: &shader,
                    entry_point: Some("vs_main"),
                    buffers: &[wgpu::VertexBufferLayout {
                        array_stride: std::mem::size_of::<Vertex>() as u64,
                        step_mode: wgpu::VertexStepMode::Vertex,
                        attributes: &[
                            wgpu::VertexAttribute {
                                offset: 0,
                                shader_location: 0,
                                format: wgpu::VertexFormat::Float32x2,
                            },
                            wgpu::VertexAttribute {
                                offset: 8,
                                shader_location: 1,
                                format: wgpu::VertexFormat::Float32x2,
                            },
                            wgpu::VertexAttribute {
                                offset: 16,
                                shader_location: 2,
                                format: wgpu::VertexFormat::Float32x4,
                            },
                            wgpu::VertexAttribute {
                                offset: 32,
                                shader_location: 3,
                                format: wgpu::VertexFormat::Float32x4,
                            },
                            wgpu::VertexAttribute {
                                offset: 48,
                                shader_location: 4,
                                format: wgpu::VertexFormat::Float32,
                            },
                        ],
                    }],
                    compilation_options: Default::default(),
                },
                fragment: Some(wgpu::FragmentState {
                    module: &shader,
                    entry_point: Some("fs_main"),
                    targets: &[Some(wgpu::ColorTargetState {
                        format: gpu.format,
                        blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                        write_mask: wgpu::ColorWrites::ALL,
                    })],
                    compilation_options: Default::default(),
                }),
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    ..Default::default()
                },
                depth_stencil: None,
                multisample: wgpu::MultisampleState::default(),
                multiview: None,
                cache: None,
            });

        Self {
            pipeline,
            bind_group_layout,
            bind_group,
            uniform_buffer,
            atlas_texture,
            atlas_view,
            sampler,
            background_texture,
            background_view,
            upload_frames: (0..UPLOAD_FRAME_COUNT).map(|_| UploadFrame::new()).collect(),
            upload_frame_index: 0,
        }
    }

    /// Render a frame with the given batch of quads.
    pub fn render_frame(
        &mut self,
        gpu: &GpuContext,
        surface: &wgpu::Surface<'_>,
        batch: &QuadBatch,
        clear_color: [f32; 4],
    ) -> Result<(), wgpu::SurfaceError> {
        if batch.vertices.is_empty() {
            // Still need to present a frame with the clear color
            let output = surface.get_current_texture()?;
            let view = output.texture.create_view(&Default::default());
            let mut encoder = gpu
                .device
                .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                    label: Some("clear_encoder"),
                });
            {
                let _pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                    label: Some("clear_pass"),
                    color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                        view: &view,
                        resolve_target: None,
                        ops: wgpu::Operations {
                            load: wgpu::LoadOp::Clear(wgpu::Color {
                                r: f64::from(clear_color[0]),
                                g: f64::from(clear_color[1]),
                                b: f64::from(clear_color[2]),
                                a: f64::from(clear_color[3]),
                            }),
                            store: wgpu::StoreOp::Store,
                        },
                    })],
                    depth_stencil_attachment: None,
                    ..Default::default()
                });
            }
            gpu.queue.submit(std::iter::once(encoder.finish()));
            output.present();
            return Ok(());
        }

        // Update uniforms
        let (w, h) = gpu.dimensions();
        gpu.queue.write_buffer(
            &self.uniform_buffer,
            0,
            bytemuck::cast_slice(&[Uniforms {
                screen_size: [w as f32, h as f32],
                _padding: [0.0; 2],
            }]),
        );

        let vertex_bytes = bytemuck::cast_slice(&batch.vertices);
        let index_bytes = bytemuck::cast_slice(&batch.indices);
        let (vertex_buffer, index_buffer) =
            self.next_upload_buffers(gpu, vertex_bytes.len() as u64, index_bytes.len() as u64);
        gpu.queue.write_buffer(&vertex_buffer, 0, vertex_bytes);
        gpu.queue.write_buffer(&index_buffer, 0, index_bytes);

        let output = surface.get_current_texture()?;
        let view = output.texture.create_view(&Default::default());
        let mut encoder = gpu
            .device
            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                label: Some("render_encoder"),
            });

        {
            let mut pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("terminal_pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color {
                            r: f64::from(clear_color[0]),
                            g: f64::from(clear_color[1]),
                            b: f64::from(clear_color[2]),
                            a: f64::from(clear_color[3]),
                        }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                ..Default::default()
            });
            pass.set_pipeline(&self.pipeline);
            pass.set_bind_group(0, &self.bind_group, &[]);
            pass.set_vertex_buffer(0, vertex_buffer.slice(..));
            pass.set_index_buffer(index_buffer.slice(..), wgpu::IndexFormat::Uint32);
            pass.draw_indexed(0..batch.indices.len() as u32, 0, 0..1);
        }

        gpu.queue.submit(std::iter::once(encoder.finish()));
        output.present();

        Ok(())
    }

    fn next_upload_buffers(
        &mut self,
        gpu: &GpuContext,
        vertex_bytes_needed: u64,
        index_bytes_needed: u64,
    ) -> (wgpu::Buffer, wgpu::Buffer) {
        let frame_index = self.upload_frame_index;
        self.upload_frame_index = (self.upload_frame_index + 1) % self.upload_frames.len();
        let frame = &mut self.upload_frames[frame_index];
        frame.ensure_buffers(gpu, vertex_bytes_needed, index_bytes_needed);
        let vertex_buffer = frame
            .vertex_buffer
            .as_ref()
            .expect("vertex buffer should exist after ensure_buffers")
            .clone();
        let index_buffer = frame
            .index_buffer
            .as_ref()
            .expect("index buffer should exist after ensure_buffers")
            .clone();
        (vertex_buffer, index_buffer)
    }

    /// Upload glyph bitmap data to the atlas texture.
    pub fn upload_glyph(
        &self,
        gpu: &GpuContext,
        x: u32,
        y: u32,
        width: u32,
        height: u32,
        data: &[u8],
    ) {
        if width == 0 || height == 0 {
            return;
        }
        gpu.queue.write_texture(
            wgpu::TexelCopyTextureInfo {
                texture: &self.atlas_texture,
                mip_level: 0,
                origin: wgpu::Origin3d { x, y, z: 0 },
                aspect: wgpu::TextureAspect::All,
            },
            data,
            wgpu::TexelCopyBufferLayout {
                offset: 0,
                bytes_per_row: Some(width),
                rows_per_image: Some(height),
            },
            wgpu::Extent3d {
                width,
                height,
                depth_or_array_layers: 1,
            },
        );
    }

    /// Upload or clear the background image texture used for the compositor.
    pub fn upload_background_image(
        &mut self,
        gpu: &GpuContext,
        width: Option<u32>,
        height: Option<u32>,
        pixels: Option<&[u8]>,
    ) {
        let (background_texture, background_view) = match (width, height, pixels) {
            (Some(width), Some(height), Some(pixels)) => {
                create_background_texture(gpu, Some((width, height, pixels)))
            }
            _ => create_background_texture(gpu, None),
        };

        self.background_texture = background_texture;
        self.background_view = background_view;
        self.bind_group = create_bind_group(
            gpu,
            &self.bind_group_layout,
            &self.uniform_buffer,
            &self.atlas_view,
            &self.background_view,
            &self.sampler,
        );
    }
}

fn grow_buffer_capacity(bytes_needed: u64) -> u64 {
    const MIN_CAPACITY: u64 = 64 * 1024;
    bytes_needed.max(MIN_CAPACITY).next_power_of_two()
}

fn create_bind_group(
    gpu: &GpuContext,
    bind_group_layout: &wgpu::BindGroupLayout,
    uniform_buffer: &wgpu::Buffer,
    atlas_view: &wgpu::TextureView,
    background_view: &wgpu::TextureView,
    sampler: &wgpu::Sampler,
) -> wgpu::BindGroup {
    gpu.device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("terminal_bind_group"),
        layout: bind_group_layout,
        entries: &[
            wgpu::BindGroupEntry {
                binding: 0,
                resource: uniform_buffer.as_entire_binding(),
            },
            wgpu::BindGroupEntry {
                binding: 1,
                resource: wgpu::BindingResource::TextureView(atlas_view),
            },
            wgpu::BindGroupEntry {
                binding: 2,
                resource: wgpu::BindingResource::Sampler(sampler),
            },
            wgpu::BindGroupEntry {
                binding: 3,
                resource: wgpu::BindingResource::TextureView(background_view),
            },
            wgpu::BindGroupEntry {
                binding: 4,
                resource: wgpu::BindingResource::Sampler(sampler),
            },
        ],
    })
}

fn create_background_texture(
    gpu: &GpuContext,
    image: Option<(u32, u32, &[u8])>,
) -> (wgpu::Texture, wgpu::TextureView) {
    let (width, height, pixels) = image.unwrap_or((1, 1, &[255u8, 255, 255, 0]));
    let texture = gpu.device.create_texture(&wgpu::TextureDescriptor {
        label: Some("background_texture"),
        size: wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
        mip_level_count: 1,
        sample_count: 1,
        dimension: wgpu::TextureDimension::D2,
        format: wgpu::TextureFormat::Rgba8UnormSrgb,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST,
        view_formats: &[],
    });
    gpu.queue.write_texture(
        wgpu::TexelCopyTextureInfo {
            texture: &texture,
            mip_level: 0,
            origin: wgpu::Origin3d::ZERO,
            aspect: wgpu::TextureAspect::All,
        },
        pixels,
        wgpu::TexelCopyBufferLayout {
            offset: 0,
            bytes_per_row: Some(width * 4),
            rows_per_image: Some(height),
        },
        wgpu::Extent3d {
            width,
            height,
            depth_or_array_layers: 1,
        },
    );
    let view = texture.create_view(&wgpu::TextureViewDescriptor::default());
    (texture, view)
}
