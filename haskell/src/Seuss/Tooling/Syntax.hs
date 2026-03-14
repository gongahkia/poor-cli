{-# LANGUAGE OverloadedStrings #-}

module Seuss.Tooling.Syntax
    ( syntaxKeywords
    ) where

import Data.Text (Text)

syntaxKeywords :: [Text]
syntaxKeywords =
    [ "timeline"
    , "entity"
    , "rel"
    , "type"
    , "let"
    , "mut"
    , "fn"
    , "if"
    , "else"
    , "match"
    , "for"
    , "in"
    , "repeat"
    , "while"
    , "return"
    , "true"
    , "false"
    , "linear"
    , "branch"
    , "parallel"
    , "loop"
    , "appears_on"
    , "kind"
    , "start"
    , "end"
    , "fork_from"
    , "merge_into"
    , "loop_count"
    ]
