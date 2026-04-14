package protocol

import "encoding/json"

type McpServer struct {
	Name      string            `json:"name"`
	Transport string            `json:"transport,omitempty"`
	Enabled   bool              `json:"enabled"`
	Command   string            `json:"command,omitempty"`
	Args      []string          `json:"args,omitempty"`
	Env       map[string]string `json:"env,omitempty"`
	URL       string            `json:"url,omitempty"`
	Headers   map[string]string `json:"headers,omitempty"`
	Tools     []string          `json:"tools,omitempty"`
	Status    string            `json:"status,omitempty"`
	Connected bool              `json:"connected,omitempty"`
	ToolCount int               `json:"toolCount,omitempty"`
	LastError string            `json:"lastError,omitempty"`
	Error     string            `json:"error,omitempty"`
}

type McpListResult struct {
	ConfigPath           string      `json:"configPath"`
	RegistryAutodiscover bool        `json:"registryAutodiscover"`
	Servers              []McpServer `json:"servers"`
}

type McpToggleParams struct {
	Name      string `json:"name"`
	Enabled   *bool  `json:"enabled,omitempty"`
	Confirmed bool   `json:"confirmed,omitempty"`
}

type McpHealth struct {
	Servers []McpHealthServer `json:"servers"`
	Error   string            `json:"error,omitempty"`
}

type McpHealthServer struct {
	Name    string `json:"name"`
	Healthy bool   `json:"healthy"`
}

type McpTestParams struct {
	Tool      string         `json:"tool,omitempty"`
	ToolName  string         `json:"toolName,omitempty"`
	Arguments map[string]any `json:"arguments,omitempty"`
}

type McpTestResult struct {
	Tool   string          `json:"tool"`
	Result json.RawMessage `json:"result"`
}
