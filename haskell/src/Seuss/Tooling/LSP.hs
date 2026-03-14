{-# LANGUAGE OverloadedStrings #-}

module Seuss.Tooling.LSP
    ( CompletionItem(..)
    , getCompletions
    , getDiagnostics
    , getHoverInfo
    ) where

import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Core.Eval
import Seuss.Core.Validation
import Seuss.Lang.Parser
import Seuss.Model.Types
import Seuss.Tooling.Syntax

data CompletionItem = CompletionItem
    { completionLabel :: Text
    , completionDetail :: Text
    }
    deriving (Eq, Show)

getCompletions :: Text -> [CompletionItem]
getCompletions prefix =
    [ CompletionItem keyword "keyword"
    | keyword <- syntaxKeywords
    , T.toLower prefix `T.isPrefixOf` T.toLower keyword
    ]

getDiagnostics :: FilePath -> Text -> [Diagnostic]
getDiagnostics file input =
    case parseProgram file input of
        Left diags -> diags
        Right program ->
            case evalProgram program of
                Left diag -> [diag]
                Right world -> validateWorld world

getHoverInfo :: FilePath -> Text -> Text -> Maybe Text
getHoverInfo file input word =
    case parseProgram file input of
        Left _ -> Nothing
        Right program ->
            case evalProgram program of
                Left _ -> Nothing
                Right world ->
                    case Map.lookup word (worldEntities world) of
                        Just entity ->
                            Just $
                                "entity "
                                    <> entityName entity
                                    <> " : "
                                    <> entityType entity
                        Nothing ->
                            case Map.lookup word (worldTimelines world) of
                                Just timeline ->
                                    Just $
                                        "timeline "
                                            <> timelineName timeline
                                            <> " ("
                                            <> T.pack (show (timelineKind timeline))
                                            <> ")"
                                Nothing -> Nothing
