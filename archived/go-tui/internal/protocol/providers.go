package protocol

type ProviderInfo struct {
	Name             string         `json:"name"`
	Model            string         `json:"model"`
	Initialized      *bool          `json:"initialized,omitempty"`
	RoutingMode      string         `json:"routingMode,omitempty"`
	Capabilities     map[string]any `json:"capabilities,omitempty"`
	SupportedClients []string       `json:"supported_clients,omitempty"`
	Tier             string         `json:"tier,omitempty"`
	CostPer1kIn      *float64       `json:"costPer1kIn,omitempty"`
	CostPer1kOut     *float64       `json:"costPer1kOut,omitempty"`
	ContextWindow    int            `json:"contextWindow,omitempty"`
	Streaming        bool           `json:"streaming,omitempty"`
	Vision           bool           `json:"vision,omitempty"`
	FunctionCall     bool           `json:"functionCall,omitempty"`
}

type SwitchProviderParams struct {
	Provider string `json:"provider"`
	Model    string `json:"model,omitempty"`
}

type SwitchProviderResult struct {
	Success            bool         `json:"success"`
	Provider           ProviderInfo `json:"provider,omitempty"`
	Error              string       `json:"error,omitempty"`
	AvailableProviders []string     `json:"availableProviders,omitempty"`
}

type ListProvidersResult map[string]ProviderDetail

type ProviderDetail struct {
	Available    bool                       `json:"available"`
	Ready        bool                       `json:"ready"`
	StatusLabel  string                     `json:"statusLabel"`
	Models       []string                   `json:"models"`
	ModelTiers   map[string]ModelTierDetail `json:"modelTiers,omitempty"`
	Capabilities []string                   `json:"capabilities,omitempty"`
}

type ModelTierDetail struct {
	Tier          string  `json:"tier"`
	Cost1kIn      float64 `json:"cost1kIn"`
	Cost1kOut     float64 `json:"cost1kOut"`
	SpeedRank     int     `json:"speedRank,omitempty"`
	ContextWindow int     `json:"contextWindow,omitempty"`
}

type SetApiKeyParams struct {
	Provider             string `json:"provider"`
	APIKey               string `json:"apiKey"`
	Persist              *bool  `json:"persist,omitempty"`
	ReloadActiveProvider *bool  `json:"reloadActiveProvider,omitempty"`
}

type SetAPIKeyParams = SetApiKeyParams

type SetAPIKeyResult struct {
	Success                bool   `json:"success"`
	Provider               string `json:"provider,omitempty"`
	EnvVar                 string `json:"envVar,omitempty"`
	Persisted              bool   `json:"persisted,omitempty"`
	ActiveProviderReloaded bool   `json:"activeProviderReloaded,omitempty"`
	MaskedKey              string `json:"maskedKey,omitempty"`
	Error                  string `json:"error,omitempty"`
}
