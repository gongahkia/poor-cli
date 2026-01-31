" poor-cli.vim
" Auto-load script for poor-cli Neovim plugin
"
" This file is loaded automatically when Neovim starts.
" The plugin is NOT initialized until you call:
"   lua require('poor-cli').setup({})
" in your init.lua or init.vim

" Prevent double-loading
if exists('g:loaded_poor_cli')
  finish
endif
let g:loaded_poor_cli = 1

" Check for Neovim
if !has('nvim')
  echohl ErrorMsg
  echo "poor-cli requires Neovim"
  echohl None
  finish
endif

" Check for minimum Neovim version (0.9+)
if !has('nvim-0.9')
  echohl WarningMsg
  echo "poor-cli works best with Neovim 0.9+. Some features may not work."
  echohl None
endif
