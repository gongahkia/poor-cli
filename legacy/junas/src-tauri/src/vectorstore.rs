use crate::error::AppError;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::AppHandle;
use tauri::Manager;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorEntry {
    pub chunk_id: String,
    pub text: String,
    pub embedding: Vec<f32>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimilarityResult {
    pub chunk_id: String,
    pub text: String,
    pub score: f32,
}
#[derive(Debug, Default, Serialize, Deserialize)]
struct VectorCollection {
    entries: Vec<VectorEntry>,
}

static STORE: Mutex<Option<HashMap<String, VectorCollection>>> = Mutex::new(None);

fn store_dir(app: &AppHandle) -> Result<PathBuf, AppError> {
    let dir = app.path().app_data_dir()
        .map_err(|e| AppError::Io(e.to_string()))?.join("vectorstore");
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}
fn collection_path(app: &AppHandle, name: &str) -> Result<PathBuf, AppError> {
    Ok(store_dir(app)?.join(format!("{name}.json")))
}
fn get_store() -> Result<std::sync::MutexGuard<'static, Option<HashMap<String, VectorCollection>>>, AppError> {
    STORE.lock().map_err(|e| AppError::Io(format!("lock poisoned: {e}")))
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() { return 0.0; }
    let dot: f32 = a.iter().zip(b).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-12);
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-12);
    dot / (norm_a * norm_b)
}

#[tauri::command]
pub fn index_document(
    app: AppHandle,
    collection: String,
    entries: Vec<VectorEntry>,
) -> Result<usize, AppError> {
    let count = entries.len();
    let mut guard = get_store()?;
    let map = guard.get_or_insert_with(HashMap::new);
    let col = map.entry(collection.clone()).or_default();
    col.entries.extend(entries);
    // persist
    let path = collection_path(&app, &collection)?;
    let data = serde_json::to_string(&col)?;
    std::fs::write(&path, data)?;
    Ok(count)
}

#[tauri::command]
pub fn query_similar(
    app: AppHandle,
    collection: String,
    query_embedding: Vec<f32>,
    top_k: usize,
) -> Result<Vec<SimilarityResult>, AppError> {
    let mut guard = get_store()?;
    let map = guard.get_or_insert_with(HashMap::new);
    // load from disk if not in memory
    if !map.contains_key(&collection) {
        let path = collection_path(&app, &collection)?;
        if path.exists() {
            let data = std::fs::read_to_string(&path)?;
            let col: VectorCollection = serde_json::from_str(&data)
                .map_err(|e| AppError::Parse(e.to_string()))?;
            map.insert(collection.clone(), col);
        } else {
            return Ok(vec![]);
        }
    }
    let col = map.get(&collection).ok_or_else(|| AppError::Io("collection not found".into()))?;
    let mut scored: Vec<SimilarityResult> = col.entries.iter().map(|e| {
        SimilarityResult {
            chunk_id: e.chunk_id.clone(),
            text: e.text.clone(),
            score: cosine_similarity(&query_embedding, &e.embedding),
        }
    }).collect();
    scored.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
    scored.truncate(top_k);
    Ok(scored)
}

#[tauri::command]
pub fn list_collections(app: AppHandle) -> Result<Vec<String>, AppError> {
    let dir = store_dir(&app)?;
    let mut names = Vec::new();
    if dir.exists() {
        for entry in std::fs::read_dir(&dir)? {
            let entry = entry?;
            if let Some(name) = entry.path().file_stem().and_then(|s| s.to_str()) {
                names.push(name.to_string());
            }
        }
    }
    Ok(names)
}

#[tauri::command]
pub fn delete_collection(app: AppHandle, collection: String) -> Result<bool, AppError> {
    let mut guard = get_store()?;
    if let Some(map) = guard.as_mut() {
        map.remove(&collection);
    }
    let path = collection_path(&app, &collection)?;
    if path.exists() {
        std::fs::remove_file(&path)?;
        return Ok(true);
    }
    Ok(false)
}
