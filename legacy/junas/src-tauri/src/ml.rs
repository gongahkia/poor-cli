use crate::error::AppError;
use futures_util::StreamExt;
use ndarray::Array2;
use ort::{session::Session, value::TensorRef};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::AppHandle;
use tauri::Manager;
use tokio::io::AsyncWriteExt;

const MODEL_CONNECT_TIMEOUT_SECS: u64 = 15;
const MODEL_REQUEST_TIMEOUT_SECS: u64 = 300;
const NER_LABELS: &[&str] = &["O", "B-MISC", "I-MISC", "B-PER", "I-PER", "B-ORG", "I-ORG", "B-LOC", "I-LOC"];
const CLASSIFY_LABELS: &[&str] = &["NEGATIVE", "POSITIVE"];
type TokenizedInputs = (Array2<i64>, Array2<i64>, Array2<i64>);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NerEntity {
    pub entity: String,
    pub word: String,
    pub start: usize,
    pub end: usize,
    pub score: f32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassifyResult {
    pub label: String,
    pub score: f32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelCacheStatus {
    pub model_type: String,
    pub exists: bool,
    pub file_path: String,
    pub size_bytes: u64,
    pub sha256: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
struct ModelCacheMetadata {
    model_type: String,
    source_url: String,
    size_bytes: u64,
    sha256: String,
    downloaded_at_unix: u64,
}

struct ModelAssetSpec {
    model_id: &'static str,
    model_url: &'static str,
    tokenizer_url: Option<&'static str>,
}

fn models_dir(app: &AppHandle) -> Result<PathBuf, AppError> {
    let dir = app.path().app_data_dir()
        .map_err(|e| AppError::Io(e.to_string()))?.join("models");
    std::fs::create_dir_all(&dir)?;
    Ok(dir)
}
fn model_file_path(app: &AppHandle, model_type: &str) -> Result<PathBuf, AppError> {
    Ok(models_dir(app)?.join(format!("{}.onnx", model_type)))
}
fn tokenizer_file_path(app: &AppHandle, model_type: &str) -> Result<PathBuf, AppError> {
    Ok(models_dir(app)?.join(format!("{}_tokenizer.json", model_type)))
}
fn metadata_file_path(app: &AppHandle, model_type: &str) -> Result<PathBuf, AppError> {
    Ok(models_dir(app)?.join(format!("{}.json", model_type)))
}

fn model_asset_spec(model_type: &str) -> Result<ModelAssetSpec, AppError> {
    let spec = match model_type {
        "chat" | "summarization" => ModelAssetSpec {
            model_id: "Xenova/distilbart-cnn-6-6",
            model_url: "https://huggingface.co/Xenova/distilbart-cnn-6-6/resolve/main/onnx/encoder_model_quantized.onnx",
            tokenizer_url: Some("https://huggingface.co/Xenova/distilbart-cnn-6-6/resolve/main/tokenizer.json"),
        },
        "ner" => ModelAssetSpec {
            model_id: "Xenova/bert-base-NER",
            model_url: "https://huggingface.co/Xenova/bert-base-NER/resolve/main/onnx/model_quantized.onnx",
            tokenizer_url: Some("https://huggingface.co/Xenova/bert-base-NER/resolve/main/tokenizer.json"),
        },
        "embeddings" => ModelAssetSpec {
            model_id: "Xenova/all-MiniLM-L6-v2",
            model_url: "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_quantized.onnx",
            tokenizer_url: Some("https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json"),
        },
        "text-classification" => ModelAssetSpec {
            model_id: "Xenova/distilbert-base-uncased-finetuned-sst-2-english",
            model_url: "https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/resolve/main/onnx/model_quantized.onnx",
            tokenizer_url: Some("https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/resolve/main/tokenizer.json"),
        },
        _ => return Err(AppError::Provider(format!("unsupported model type: {model_type}"))),
    };
    Ok(spec)
}

fn now_unix_seconds() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}
fn compute_sha256(path: &Path) -> Result<String, AppError> {
    let mut file = std::fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let bytes_read = file.read(&mut buffer)?;
        if bytes_read == 0 { break; }
        hasher.update(&buffer[..bytes_read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}
async fn write_metadata(path: &Path, metadata: &ModelCacheMetadata) -> Result<(), AppError> {
    let serialized = serde_json::to_string_pretty(metadata)?;
    tokio::fs::write(path, serialized).await.map_err(|e| AppError::Io(e.to_string()))
}
async fn read_metadata(path: &Path) -> Result<Option<ModelCacheMetadata>, AppError> {
    if !path.exists() { return Ok(None); }
    let raw = tokio::fs::read_to_string(path).await.map_err(|e| AppError::Io(e.to_string()))?;
    let parsed = serde_json::from_str::<ModelCacheMetadata>(&raw).map_err(|e| AppError::Parse(e.to_string()))?;
    Ok(Some(parsed))
}
async fn refresh_metadata(app: &AppHandle, model_type: &str, source_url: &str) -> Result<(), AppError> {
    let path = model_file_path(app, model_type)?;
    if !path.exists() { return Ok(()); }
    let size_bytes = std::fs::metadata(&path)?.len();
    let sha256 = compute_sha256(&path)?;
    let metadata = ModelCacheMetadata {
        model_type: model_type.to_string(),
        source_url: source_url.to_string(),
        size_bytes, sha256,
        downloaded_at_unix: now_unix_seconds(),
    };
    write_metadata(&metadata_file_path(app, model_type)?, &metadata).await
}

async fn download_file(client: &reqwest::Client, url: &str, target: &Path) -> Result<u64, AppError> {
    let tmp = target.with_extension("download");
    let response = client.get(url).send().await?;
    if !response.status().is_success() {
        return Err(AppError::Network(format!("download failed: HTTP {}", response.status())));
    }
    let mut stream = response.bytes_stream();
    let mut out = tokio::fs::File::create(&tmp).await.map_err(|e| AppError::Io(e.to_string()))?;
    let mut total: u64 = 0;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(AppError::from)?;
        total += chunk.len() as u64;
        out.write_all(&chunk).await.map_err(|e| AppError::Io(e.to_string()))?;
    }
    out.flush().await.map_err(|e| AppError::Io(e.to_string()))?;
    drop(out);
    tokio::fs::rename(&tmp, target).await.map_err(|e| AppError::Io(e.to_string()))?;
    Ok(total)
}

#[tauri::command]
pub async fn download_model(app: AppHandle, model_type: String) -> Result<String, AppError> {
    let spec = model_asset_spec(&model_type)?;
    let target_path = model_file_path(&app, &model_type)?;
    let metadata_path = metadata_file_path(&app, &model_type)?;
    if target_path.exists() {
        refresh_metadata(&app, &model_type, spec.model_url).await?;
        // ensure tokenizer is also present
        if let Some(tok_url) = spec.tokenizer_url {
            let tok_path = tokenizer_file_path(&app, &model_type)?;
            if !tok_path.exists() {
                let client = reqwest::Client::builder()
                    .connect_timeout(std::time::Duration::from_secs(MODEL_CONNECT_TIMEOUT_SECS))
                    .timeout(std::time::Duration::from_secs(MODEL_REQUEST_TIMEOUT_SECS))
                    .build().map_err(|e| AppError::Network(e.to_string()))?;
                download_file(&client, tok_url, &tok_path).await?;
            }
        }
        return Ok(format!("model {model_type} already cached at {}", target_path.display()));
    }
    let client = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(MODEL_CONNECT_TIMEOUT_SECS))
        .timeout(std::time::Duration::from_secs(MODEL_REQUEST_TIMEOUT_SECS))
        .build().map_err(|e| AppError::Network(e.to_string()))?;
    // download model
    let total_bytes = download_file(&client, spec.model_url, &target_path).await?;
    let sha256 = compute_sha256(&target_path)?;
    let metadata = ModelCacheMetadata {
        model_type: model_type.clone(),
        source_url: spec.model_url.to_string(),
        size_bytes: total_bytes, sha256,
        downloaded_at_unix: now_unix_seconds(),
    };
    write_metadata(&metadata_path, &metadata).await?;
    // download tokenizer
    if let Some(tok_url) = spec.tokenizer_url {
        let tok_path = tokenizer_file_path(&app, &model_type)?;
        download_file(&client, tok_url, &tok_path).await?;
    }
    Ok(format!("model {model_type} ({}) downloaded to {}", spec.model_id, target_path.display()))
}

#[tauri::command]
pub async fn get_model_status(app: AppHandle, model_type: String) -> Result<ModelCacheStatus, AppError> {
    let model_path = model_file_path(&app, &model_type)?;
    let metadata_path = metadata_file_path(&app, &model_type)?;
    let exists = model_path.exists();
    let size_bytes = if exists { std::fs::metadata(&model_path)?.len() } else { 0 };
    let metadata = read_metadata(&metadata_path).await?;
    let sha256 = metadata.map(|e| e.sha256).or_else(|| {
        if exists { compute_sha256(&model_path).ok() } else { None }
    });
    Ok(ModelCacheStatus { model_type, exists, file_path: model_path.display().to_string(), size_bytes, sha256 })
}

#[tauri::command]
pub async fn remove_model_cache(app: AppHandle, model_type: String) -> Result<bool, AppError> {
    let mut removed = false;
    for path in [
        model_file_path(&app, &model_type)?,
        metadata_file_path(&app, &model_type)?,
        tokenizer_file_path(&app, &model_type)?,
    ] {
        if path.exists() {
            tokio::fs::remove_file(&path).await.map_err(|e| AppError::Io(e.to_string()))?;
            removed = true;
        }
    }
    Ok(removed)
}

#[tauri::command]
pub async fn clear_model_cache(app: AppHandle) -> Result<(), AppError> {
    let dir = models_dir(&app)?;
    if dir.exists() {
        tokio::fs::remove_dir_all(&dir).await.map_err(|e| AppError::Io(e.to_string()))?;
    }
    tokio::fs::create_dir_all(&dir).await.map_err(|e| AppError::Io(e.to_string()))
}

#[tauri::command]
pub fn is_onnx_runtime_available() -> bool {
    Session::builder().is_ok() // actually probe runtime availability
}

#[tauri::command]
pub async fn load_model(app: AppHandle, model_type: String) -> Result<String, AppError> {
    let status = get_model_status(app.clone(), model_type.clone()).await?;
    if !status.exists {
        return Err(AppError::Io(format!("model file not found for {model_type}. Download it from Config > Models.")));
    }
    let spec = model_asset_spec(&model_type)?;
    refresh_metadata(&app, &model_type, spec.model_url).await?;
    Ok(format!("model {model_type} ready at {}", status.file_path))
}

// -- inference helpers --

fn create_session(model_path: &Path) -> Result<Session, AppError> {
    Session::builder()
        .map_err(|e| AppError::Provider(format!("ONNX Runtime unavailable: {e}")))?
        .commit_from_file(model_path)
        .map_err(|e| AppError::Provider(format!("failed to load model: {e}")))
}
fn load_tokenizer(path: &Path) -> Result<tokenizers::Tokenizer, AppError> {
    tokenizers::Tokenizer::from_file(path)
        .map_err(|e| AppError::Provider(format!("failed to load tokenizer: {e}")))
}
fn ensure_model_and_tokenizer(app: &AppHandle, model_type: &str) -> Result<(PathBuf, PathBuf), AppError> {
    let mp = model_file_path(app, model_type)?;
    let tp = tokenizer_file_path(app, model_type)?;
    if !mp.exists() {
        return Err(AppError::Provider(format!("model {model_type} not downloaded. Go to Config > Models.")));
    }
    if !tp.exists() {
        return Err(AppError::Provider(format!("tokenizer for {model_type} not found. Re-download from Config > Models.")));
    }
    Ok((mp, tp))
}

fn softmax(logits: &[f32]) -> Vec<f32> {
    let max = logits.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
    let exps: Vec<f32> = logits.iter().map(|&x| (x - max).exp()).collect();
    let sum: f32 = exps.iter().sum();
    exps.iter().map(|&e| e / sum).collect()
}

fn tokenize_to_arrays(tokenizer: &tokenizers::Tokenizer, text: &str, max_len: usize)
    -> Result<TokenizedInputs, AppError>
{
    let encoding = tokenizer.encode(text, true)
        .map_err(|e| AppError::Provider(format!("tokenization failed: {e}")))?;
    let len = encoding.get_ids().len().min(max_len);
    let ids: Vec<i64> = encoding.get_ids()[..len].iter().map(|&x| x as i64).collect();
    let mask: Vec<i64> = encoding.get_attention_mask()[..len].iter().map(|&x| x as i64).collect();
    let type_ids: Vec<i64> = encoding.get_type_ids()[..len].iter().map(|&x| x as i64).collect();
    Ok((
        Array2::from_shape_vec((1, len), ids).map_err(|e| AppError::Provider(e.to_string()))?,
        Array2::from_shape_vec((1, len), mask).map_err(|e| AppError::Provider(e.to_string()))?,
        Array2::from_shape_vec((1, len), type_ids).map_err(|e| AppError::Provider(e.to_string()))?,
    ))
}

// -- inference commands --

#[tauri::command]
pub fn run_ner(app: AppHandle, text: String) -> Result<Vec<NerEntity>, AppError> {
    let (mp, tp) = ensure_model_and_tokenizer(&app, "ner")?;
    let mut session = create_session(&mp)?;
    let tokenizer = load_tokenizer(&tp)?;
    let (input_ids, attention_mask, token_type_ids) = tokenize_to_arrays(&tokenizer, &text, 512)?;
    let input_ids_shape = [1usize, input_ids.ncols()];
    let input_ids_data = input_ids.as_slice().ok_or_else(|| AppError::Provider("non-contiguous input_ids".into()))?;
    let attention_mask_shape = [1usize, attention_mask.ncols()];
    let attention_mask_data =
        attention_mask.as_slice().ok_or_else(|| AppError::Provider("non-contiguous attention_mask".into()))?;
    let token_type_ids_shape = [1usize, token_type_ids.ncols()];
    let token_type_ids_data =
        token_type_ids.as_slice().ok_or_else(|| AppError::Provider("non-contiguous token_type_ids".into()))?;
    let outputs = session.run(ort::inputs! {
        "input_ids" => TensorRef::from_array_view((input_ids_shape, input_ids_data)).map_err(|e| AppError::Provider(e.to_string()))?,
        "attention_mask" => TensorRef::from_array_view((attention_mask_shape, attention_mask_data))
            .map_err(|e| AppError::Provider(e.to_string()))?,
        "token_type_ids" => TensorRef::from_array_view((token_type_ids_shape, token_type_ids_data))
            .map_err(|e| AppError::Provider(e.to_string()))?
    })
        .map_err(|e| AppError::Provider(format!("NER inference failed: {e}")))?;
    let (shape, logits) = outputs[0].try_extract_tensor::<f32>()
        .map_err(|e| AppError::Provider(format!("output extraction failed: {e}")))?;
    if shape.len() != 3 || shape[0] != 1 {
        return Err(AppError::Provider(format!("unexpected NER output shape: {shape}")));
    }
    let seq_len = shape[1] as usize;
    let num_labels = shape[2] as usize;
    let encoding = tokenizer.encode(text.as_str(), true)
        .map_err(|e| AppError::Provider(format!("re-tokenization failed: {e}")))?;
    let tokens = encoding.get_tokens();
    let offsets = encoding.get_offsets();
    let mut entities = Vec::new();
    for i in 0..seq_len.min(tokens.len()) {
        let base = i * num_labels;
        let token_logits = logits[base..base + num_labels].to_vec();
        let probs = softmax(&token_logits);
        let best_idx = probs.iter().enumerate().max_by(|a, b| a.1.partial_cmp(b.1).unwrap()).map(|(i, _)| i).unwrap_or(0);
        if best_idx == 0 { continue; } // O label
        let label = NER_LABELS.get(best_idx).unwrap_or(&"O");
        if *label == "O" { continue; }
        let (start, end) = offsets[i];
        let word = if start < text.len() && end <= text.len() {
            text[start..end].to_string()
        } else {
            tokens[i].replace("##", "")
        };
        if word.is_empty() || word == "[CLS]" || word == "[SEP]" { continue; }
        entities.push(NerEntity {
            entity: label.to_string(), word,
            start, end, score: probs[best_idx],
        });
    }
    Ok(entities)
}

#[tauri::command]
pub fn run_summarize(_app: AppHandle, _text: String, _max_length: u32) -> Result<String, AppError> {
    Err(AppError::Provider(
        "Summarization requires a seq2seq model (encoder + decoder). \
         Use /summarize-document for AI-powered summarization or \
         /summarize-local with the local NLP fallback.".into(),
    ))
}

#[tauri::command]
pub fn run_classify(app: AppHandle, text: String) -> Result<Vec<ClassifyResult>, AppError> {
    let (mp, tp) = ensure_model_and_tokenizer(&app, "text-classification")?;
    let mut session = create_session(&mp)?;
    let tokenizer = load_tokenizer(&tp)?;
    let (input_ids, attention_mask, _) = tokenize_to_arrays(&tokenizer, &text, 512)?;
    let input_ids_shape = [1usize, input_ids.ncols()];
    let input_ids_data = input_ids.as_slice().ok_or_else(|| AppError::Provider("non-contiguous input_ids".into()))?;
    let attention_mask_shape = [1usize, attention_mask.ncols()];
    let attention_mask_data =
        attention_mask.as_slice().ok_or_else(|| AppError::Provider("non-contiguous attention_mask".into()))?;
    let outputs = session.run(ort::inputs! {
        "input_ids" => TensorRef::from_array_view((input_ids_shape, input_ids_data)).map_err(|e| AppError::Provider(e.to_string()))?,
        "attention_mask" => TensorRef::from_array_view((attention_mask_shape, attention_mask_data))
            .map_err(|e| AppError::Provider(e.to_string()))?
    })
        .map_err(|e| AppError::Provider(format!("classification inference failed: {e}")))?;
    let (shape, logits) = outputs[0].try_extract_tensor::<f32>()
        .map_err(|e| AppError::Provider(format!("output extraction failed: {e}")))?;
    let logit_slice = match shape.len() {
        1 => logits,
        2 if shape[0] == 1 => {
            let num_labels = shape[1] as usize;
            &logits[..num_labels]
        }
        _ => return Err(AppError::Provider(format!("unexpected classification output shape: {shape}"))),
    };
    let probs = softmax(logit_slice);
    let mut results: Vec<ClassifyResult> = probs.iter().enumerate()
        .map(|(i, &score)| ClassifyResult {
            label: CLASSIFY_LABELS.get(i).unwrap_or(&"UNKNOWN").to_string(),
            score,
        }).collect();
    results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
    Ok(results)
}

#[tauri::command]
pub fn run_embeddings(app: AppHandle, text: String) -> Result<Vec<f32>, AppError> {
    let (mp, tp) = ensure_model_and_tokenizer(&app, "embeddings")?;
    let mut session = create_session(&mp)?;
    let tokenizer = load_tokenizer(&tp)?;
    let (input_ids, attention_mask, token_type_ids) = tokenize_to_arrays(&tokenizer, &text, 512)?;
    let mask_f32 = attention_mask.mapv(|x| x as f32);
    let input_ids_shape = [1usize, input_ids.ncols()];
    let input_ids_data = input_ids.as_slice().ok_or_else(|| AppError::Provider("non-contiguous input_ids".into()))?;
    let attention_mask_shape = [1usize, attention_mask.ncols()];
    let attention_mask_data =
        attention_mask.as_slice().ok_or_else(|| AppError::Provider("non-contiguous attention_mask".into()))?;
    let token_type_ids_shape = [1usize, token_type_ids.ncols()];
    let token_type_ids_data =
        token_type_ids.as_slice().ok_or_else(|| AppError::Provider("non-contiguous token_type_ids".into()))?;
    let outputs = session.run(ort::inputs! {
        "input_ids" => TensorRef::from_array_view((input_ids_shape, input_ids_data)).map_err(|e| AppError::Provider(e.to_string()))?,
        "attention_mask" => TensorRef::from_array_view((attention_mask_shape, attention_mask_data))
            .map_err(|e| AppError::Provider(e.to_string()))?,
        "token_type_ids" => TensorRef::from_array_view((token_type_ids_shape, token_type_ids_data))
            .map_err(|e| AppError::Provider(e.to_string()))?
    })
        .map_err(|e| AppError::Provider(format!("embeddings inference failed: {e}")))?;
    let (shape, hidden) = outputs[0].try_extract_tensor::<f32>()
        .map_err(|e| AppError::Provider(format!("output extraction failed: {e}")))?;
    if shape.len() != 3 || shape[0] != 1 {
        return Err(AppError::Provider(format!("unexpected embeddings output shape: {shape}")));
    }
    let seq_len = shape[1] as usize;
    let hidden_dim = shape[2] as usize;
    // mean pooling: sum(hidden * mask) / sum(mask)
    let mut pooled = vec![0.0f32; hidden_dim];
    let mask_sum: f32 = mask_f32.iter().sum::<f32>().max(1.0);
    for s in 0..seq_len {
        let m = mask_f32[[0, s]];
        if m == 0.0 { continue; }
        let base = s * hidden_dim;
        for d in 0..hidden_dim {
            pooled[d] += hidden[base + d] * m;
        }
    }
    for value in &mut pooled {
        *value /= mask_sum;
    }
    // L2 normalize
    let norm: f32 = pooled.iter().map(|x| x * x).sum::<f32>().sqrt().max(1e-12);
    for value in &mut pooled {
        *value /= norm;
    }
    Ok(pooled)
}
