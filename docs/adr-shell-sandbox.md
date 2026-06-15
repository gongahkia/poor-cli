# ADR: Shell Sandbox Parser

## Decision

Use Python `shlex` only for lexical tokenization and deny shell features whose execution semantics require a full shell parser.

## Rationale

The shell tool is a convenience path, not a general Bash interpreter. A partial Bash parser is more dangerous than a narrow deny policy because command substitution, process substitution, heredocs, aliases, functions, and shell wrappers can hide network calls or writes outside the workdir.

## Policy

The sandbox blocks unsupported shell syntax before execution, blocks URL-like arguments and known network commands, validates write paths for file-mutating commands and redirects, and records deny reasons in tool artifacts.
