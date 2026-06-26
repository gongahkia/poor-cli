export type Vec3 = [number, number, number];

export type LayoutItem = {
  id?: string;
  type: 'wall' | 'furniture' | 'model_part' | 'reference_image' | 'opening' | string;
  pos: Vec3;
  geo: Vec3;
  rot?: number;
  visible?: boolean;
  color?: number;
  name?: string;
  room?: string;
  furnitureType?: string | null;
  locked?: boolean;
  catalog?: Record<string, unknown>;
  texture_data_url?: string;
  label?: string;
  source?: string;
  [key: string]: unknown;
};

export type LayoutData = {
  version: number;
  schema?: string;
  layout_schema_version?: number;
  metadata?: Record<string, unknown>;
  items: LayoutItem[];
  rooms?: Array<Record<string, unknown>>;
  assumptions?: unknown[];
  validation_reports?: unknown[];
  exports?: unknown[];
  layout_versions?: unknown[];
  scenarios?: unknown[];
  disclaimers?: string[];
  _stamp?: number;
  [key: string]: unknown;
};

export type ProjectRecord = {
  id: string;
  title: string;
  journey: string;
  updatedAt: string;
  layout: LayoutData;
  transcript: TranscriptEntry[];
  assets?: Record<string, unknown>;
};

export type TranscriptEntry = {
  role: 'user' | 'assistant' | 'tool' | 'error';
  text: string;
  at: string;
};

export type ChatHistoryMessage = {
  role: 'user' | 'assistant';
  content: string | Array<Record<string, unknown>>;
};

export type ProviderSpec = {
  id: string;
  label: string;
  requires_api_key: boolean;
  command_available: boolean | null;
  capabilities: string[];
  models?: Array<{ id: string; label: string; default?: boolean; capabilities?: string[] }>;
  install_hint?: string;
};

export type ChatStatus = {
  available: boolean;
  providers_with_env_keys: string[];
  supported_providers: string[];
  default_models: Record<string, string>;
  providers: ProviderSpec[];
  capabilities: Record<string, unknown>;
};

export type ChatAction = {
  tool: string;
  args?: Record<string, unknown>;
  result: string;
  result_json?: Record<string, unknown>;
  elapsed_ms?: number;
};

export type ChatResponse = {
  response: string;
  result?: string;
  history?: ChatHistoryMessage[];
  provider?: string;
  model?: string;
  actions?: ChatAction[];
  pending_plan?: Record<string, unknown>;
  request_id?: string;
  conversation_id?: string;
  error?: string;
};

export type CatalogItem = {
  id: string;
  name: string;
  category?: string;
  price?: number | string;
  currency?: string;
  dimensions?: Record<string, number>;
  url?: string;
  source?: string;
  [key: string]: unknown;
};

export type ToolSpec = {
  name: string;
  description?: string;
  parameters?: Record<string, unknown>;
};

export type StoredKeys = Record<string, string>;

export function emptyLayout(): LayoutData {
  return {
    version: 1,
    schema: 'haus.layout.v2',
    layout_schema_version: 2,
    items: [],
    rooms: [],
    _stamp: Date.now(),
  };
}

export function withIds(layout: LayoutData): LayoutData {
  return {
    ...layout,
    version: Number(layout.version || 1),
    schema: layout.schema || 'haus.layout.v2',
    layout_schema_version: Number(layout.layout_schema_version || 2),
    items: (Array.isArray(layout.items) ? layout.items : []).map((item, index) => ({
      ...item,
      id: item.id || `item-${Date.now().toString(16)}-${index}`,
      rot: Number(item.rot || 0),
      visible: item.visible !== false,
    })),
    _stamp: Date.now(),
  };
}
