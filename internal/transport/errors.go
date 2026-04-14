package transport

import "errors"

var (
	ErrMissingContentLength = errors.New("transport: missing Content-Length header")
	ErrIncompleteHeader     = errors.New("transport: incomplete header")
	ErrIncompleteBody       = errors.New("transport: incomplete body")
	ErrHeaderTooLarge       = errors.New("transport: header exceeds 64 KB")
	ErrNegativeLength       = errors.New("transport: negative Content-Length")
)
