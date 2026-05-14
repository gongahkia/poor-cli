export interface ModelDef {
  id: string;
  name: string;
  description: string;
  size: string;
  sizeBytes: number; // approximate
  modelUrl: string;
  tokenizerUrl: string;
  task: "ner" | "classification" | "embeddings" | "summarization" | "chat";
}

export const LOCAL_MODELS: ModelDef[] = [
  {
    id: "chat",
    name: "Local Chat (LaMini)",
    description: "General purpose chat and instruction following",
    size: "~250MB",
    sizeBytes: 250_000_000,
    modelUrl: "https://huggingface.co/Xenova/LaMini-Flan-T5-248M/resolve/main/onnx/encoder_model_quantized.onnx",
    tokenizerUrl: "https://huggingface.co/Xenova/LaMini-Flan-T5-248M/resolve/main/tokenizer.json",
    task: "chat",
  },
  {
    id: "summarization",
    name: "Summarization",
    description: "Summarize long legal documents into concise summaries",
    size: "~300MB",
    sizeBytes: 300_000_000,
    modelUrl: "https://huggingface.co/Xenova/distilbart-cnn-6-6/resolve/main/onnx/encoder_model_quantized.onnx",
    tokenizerUrl: "https://huggingface.co/Xenova/distilbart-cnn-6-6/resolve/main/tokenizer.json",
    task: "summarization",
  },
  {
    id: "ner",
    name: "Named Entity Recognition",
    description: "Advanced entity extraction (people, organizations, locations)",
    size: "~400MB",
    sizeBytes: 400_000_000,
    modelUrl: "https://huggingface.co/Xenova/bert-base-NER/resolve/main/onnx/model_quantized.onnx",
    tokenizerUrl: "https://huggingface.co/Xenova/bert-base-NER/resolve/main/tokenizer.json",
    task: "ner",
  },
  {
    id: "embeddings",
    name: "Text Embeddings",
    description: "Generate embeddings for semantic search and similarity",
    size: "~80MB",
    sizeBytes: 80_000_000,
    modelUrl: "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_quantized.onnx",
    tokenizerUrl: "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json",
    task: "embeddings",
  },
  {
    id: "text-classification",
    name: "Text Classification",
    description: "Classify text sentiment and categories",
    size: "~250MB",
    sizeBytes: 250_000_000,
    modelUrl: "https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/resolve/main/onnx/model_quantized.onnx",
    tokenizerUrl: "https://huggingface.co/Xenova/distilbert-base-uncased-finetuned-sst-2-english/resolve/main/tokenizer.json",
    task: "classification",
  },
];
