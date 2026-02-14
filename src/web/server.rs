use axum::{Router, routing::get, response::Html, extract::State};
use std::sync::{Arc, RwLock};
use tower_http::cors::CorsLayer;
use tokio::sync::broadcast;

/// Shared state for web server
pub struct AppState {
    pub svg_content: RwLock<String>,
    pub tx: broadcast::Sender<String>,
}

/// Start the web server (Tasks 17, 20-25)
pub async fn start_server(port: u16, initial_svg: String) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let (tx, _) = broadcast::channel(16);
    let state = Arc::new(AppState {
        svg_content: RwLock::new(initial_svg),
        tx,
    });

    let app = Router::new()
        .route("/", get(index_handler))
        .route("/timeline.svg", get(svg_handler))
        .route("/ws", get(ws_handler))
        .layer(CorsLayer::permissive())
        .with_state(state);

    let addr = format!("0.0.0.0:{}", port);
    eprintln!("Serving at http://localhost:{}", port);

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    Ok(())
}

async fn index_handler(State(state): State<Arc<AppState>>) -> Html<String> {
    let svg = state.svg_content.read().unwrap().clone();
    Html(generate_viewer_html(&svg))
}

async fn svg_handler(State(state): State<Arc<AppState>>) -> String {
    state.svg_content.read().unwrap().clone()
}

async fn ws_handler(
    ws: axum::extract::WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl axum::response::IntoResponse {
    ws.on_upgrade(move |socket| handle_ws(socket, state))
}

async fn handle_ws(mut socket: axum::extract::ws::WebSocket, state: Arc<AppState>) {
    let mut rx = state.tx.subscribe();
    while let Ok(msg) = rx.recv().await {
        if socket.send(axum::extract::ws::Message::Text(msg.into())).await.is_err() {
            break;
        }
    }
}

/// Update SVG and notify WebSocket clients
pub fn update_svg(state: &Arc<AppState>, new_svg: String) {
    *state.svg_content.write().unwrap() = new_svg.clone();
    let _ = state.tx.send(new_svg);
}

async fn shutdown_signal() {
    tokio::signal::ctrl_c().await.ok();
    eprintln!("\nShutting down...");
}

fn generate_viewer_html(svg: &str) -> String {
    format!(r##"<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Chron Timeline Viewer</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; color: #eee; font-family: system-ui; overflow: hidden; }}
  #toolbar {{ position: fixed; top: 0; left: 0; right: 0; height: 40px; background: #16213e; display: flex; align-items: center; padding: 0 16px; gap: 12px; z-index: 100; }}
  #toolbar button {{ background: #0f3460; color: #eee; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; }}
  #toolbar button:hover {{ background: #533483; }}
  #sidebar {{ position: fixed; left: 0; top: 40px; bottom: 0; width: 0; background: #16213e; overflow-y: auto; transition: width 0.2s; z-index: 50; }}
  #sidebar.open {{ width: 250px; padding: 12px; }}
  #sidebar h3 {{ margin-bottom: 8px; }}
  #sidebar label {{ display: block; margin: 4px 0; cursor: pointer; }}
  #container {{ position: fixed; top: 40px; left: 0; right: 0; bottom: 40px; overflow: auto; cursor: grab; }}
  #container.dragging {{ cursor: grabbing; }}
  #timeline {{ transform-origin: 0 0; }}
  #scrubber {{ position: fixed; bottom: 0; left: 0; right: 0; height: 40px; background: #16213e; display: flex; align-items: center; padding: 0 16px; }}
  #scrubber input {{ flex: 1; margin: 0 12px; }}
  #detail {{ display: none; position: fixed; background: #16213e; border: 1px solid #533483; border-radius: 8px; padding: 12px; max-width: 300px; z-index: 200; }}
  .entity-bar:hover {{ opacity: 0.8; cursor: pointer; }}
  .edge:hover {{ stroke-width: 3; }}
</style>
</head>
<body>
<div id="toolbar">
  <button onclick="toggleSidebar()">☰ Filter</button>
  <button onclick="resetView()">⟳ Reset</button>
  <button onclick="exportSVG()">💾 Export SVG</button>
  <span id="zoom-label">100%</span>
</div>
<div id="sidebar">
  <h3>Filters</h3>
  <div id="filter-list"></div>
</div>
<div id="container">
  <div id="timeline">{svg}</div>
</div>
<div id="scrubber">
  <span>Time:</span>
  <input type="range" id="time-slider" min="0" max="100" value="50">
  <span id="time-label">50</span>
</div>
<div id="detail"></div>
<script>
let scale = 1, panX = 0, panY = 0, dragging = false, lastX, lastY;
const container = document.getElementById('container');
const timeline = document.getElementById('timeline');

container.addEventListener('wheel', e => {{
  e.preventDefault();
  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  scale *= delta;
  scale = Math.max(0.1, Math.min(10, scale));
  timeline.style.transform = `translate(${{panX}}px,${{panY}}px) scale(${{scale}})`;
  document.getElementById('zoom-label').textContent = Math.round(scale*100)+'%';
}});

container.addEventListener('mousedown', e => {{ dragging=true; lastX=e.clientX; lastY=e.clientY; container.classList.add('dragging'); }});
window.addEventListener('mouseup', () => {{ dragging=false; container.classList.remove('dragging'); }});
window.addEventListener('mousemove', e => {{
  if(!dragging) return;
  panX += e.clientX-lastX; panY += e.clientY-lastY;
  lastX=e.clientX; lastY=e.clientY;
  timeline.style.transform = `translate(${{panX}}px,${{panY}}px) scale(${{scale}})`;
}});

document.querySelectorAll('.entity-bar, rect[data-entity]').forEach(el => {{
  el.addEventListener('click', e => {{
    const detail = document.getElementById('detail');
    detail.style.display = 'block';
    detail.style.left = e.clientX+'px';
    detail.style.top = e.clientY+'px';
    detail.innerHTML = '<b>'+el.getAttribute('data-name')+'</b><br>Type: '+(el.getAttribute('data-type')||'entity');
  }});
}});

document.addEventListener('click', e => {{
  if(!e.target.closest('.entity-bar, rect[data-entity], #detail')) document.getElementById('detail').style.display='none';
}});

function toggleSidebar() {{ document.getElementById('sidebar').classList.toggle('open'); }}
function resetView() {{ scale=1; panX=0; panY=0; timeline.style.transform=''; document.getElementById('zoom-label').textContent='100%'; }}
function exportSVG() {{
  const svg = document.querySelector('#timeline svg');
  if(svg) {{
    const blob = new Blob([svg.outerHTML], {{type:'image/svg+xml'}});
    const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='timeline.svg'; a.click();
  }}
}}

document.getElementById('time-slider').addEventListener('input', e => {{
  document.getElementById('time-label').textContent = e.target.value;
}});

// WebSocket live reload (Task 19)
const ws = new WebSocket('ws://'+location.host+'/ws');
ws.onmessage = e => {{ timeline.innerHTML = e.data; }};
ws.onclose = () => {{ setTimeout(() => location.reload(), 2000); }};
</script>
</body>
</html>"##)
}
