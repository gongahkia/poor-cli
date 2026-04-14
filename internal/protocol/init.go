package protocol

type InitializeParams struct {
	Provider           string         `json:"provider,omitempty"`
	Model              string         `json:"model,omitempty"`
	APIKey             string         `json:"apiKey,omitempty"`
	Streaming          *bool          `json:"streaming,omitempty"`
	PermissionMode     string         `json:"permissionMode,omitempty"`
	SandboxPreset      string         `json:"sandboxPreset,omitempty"`
	ClientCapabilities map[string]any `json:"clientCapabilities,omitempty"`
}

type InitializeResult struct {
	Capabilities Capabilities `json:"capabilities"`
}

type Capabilities struct {
	CompletionProvider          bool            `json:"completionProvider,omitempty"`
	InlineCompletionProvider    bool            `json:"inlineCompletionProvider,omitempty"`
	CompletionStreamingProvider bool            `json:"completionStreamingProvider,omitempty"`
	ChatProvider                bool            `json:"chatProvider,omitempty"`
	ChatStreamingProvider       bool            `json:"chatStreamingProvider,omitempty"`
	FileOperations              bool            `json:"fileOperations,omitempty"`
	PermissionMode              string          `json:"permissionMode,omitempty"`
	SandboxPreset               string          `json:"sandboxPreset,omitempty"`
	ServerLogPath               string          `json:"serverLogPath,omitempty"`
	ProviderInfo                *ProviderInfo   `json:"providerInfo,omitempty"`
	GuardedFlow                 *GuardedFlow    `json:"guardedFlow,omitempty"`
	Security                    *SecurityCaps   `json:"security,omitempty"`
	RepoIndex                   *RepoIndexStats `json:"repoIndex,omitempty"`
	NeedsAPIKey                 bool            `json:"needsApiKey,omitempty"`
	Message                     string          `json:"message,omitempty"`
}

type GuardedFlow struct {
	PermissionRequests bool `json:"permissionRequests"`
	PlanReview         bool `json:"planReview"`
}

type SecurityCaps struct {
	TrustedWorkspaceBoundary bool     `json:"trustedWorkspaceBoundary"`
	TrustedRoots             []string `json:"trustedRoots"`
}

type RepoIndexStats struct {
	Files   int    `json:"files"`
	Symbols int    `json:"symbols"`
	Status  string `json:"status"`
}
