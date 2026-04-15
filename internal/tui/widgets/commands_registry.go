package widgets

import "github.com/gongahkia/gocli-poor/internal/tui/widgets/commands"

type Command = commands.Command
type Origin = commands.Origin
type Registry = commands.Registry

const (
	OriginBuiltin = commands.OriginBuiltin
	OriginCustom  = commands.OriginCustom
	Builtin       = commands.Builtin
	Custom        = commands.Custom
)

func NewRegistry() *commands.Registry {
	return commands.NewRegistry()
}
