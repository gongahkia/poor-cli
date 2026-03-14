{-# LANGUAGE OverloadedStrings #-}

module Seuss.Import.CSV
    ( importCsvToSeuss
    ) where

import Data.Char (isSpace)
import Data.List (elemIndex)
import Data.Maybe (fromMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Model.Types

importCsvToSeuss :: Text -> Either [Diagnostic] Text
importCsvToSeuss input
    | null rows =
        Left [diag 0 "empty CSV"]
    | hasColumn "source" && hasColumn "target" =
        importRelationships header dataRows
    | hasColumn "name" && hasColumn "timeline" =
        importEntities header dataRows
    | otherwise =
        Left [diag 1 "unsupported CSV schema; expected entity or relationship columns"]
  where
    rows = filter (not . T.null) (map T.stripEnd (T.lines input))
    header =
        case rows of
            [] -> []
            firstRow : _ -> parseCsvFields firstRow
    dataRows = zip [2 ..] (map parseCsvFields (drop 1 rows))
    hasColumn name = name `elem` header

importEntities :: [Text] -> [(Int, [Text])] -> Either [Diagnostic] Text
importEntities header rows =
    case missingRequired of
        [] -> render <$> traverse renderRow rows
        missing ->
            Left [diag 1 ("missing required columns: " <> T.intercalate ", " missing)]
  where
    missingRequired = filter (`notElem` header) ["name", "type", "timeline", "start", "end"]
    render blocks = T.intercalate "\n\n" blocks <> "\n"
    renderRow (lineNumber, columns) =
        if T.null nameValue
            then Left (diag lineNumber "empty name")
            else Right $
                T.unlines $
                    [ "entity " <> nameValue <> " : " <> defaultedType <> " {"
                    ]
                        ++ attributeLines
                        ++ [ "    appears_on: " <> timelineValue <> " @ " <> startValue <> ".." <> endValue <> ","
                           , "}"
                           ]
      where
        lookupColumn label = columnValue header columns label
        nameValue = lookupColumn "name"
        defaultedType = defaultText "entity" (lookupColumn "type")
        timelineValue = lookupColumn "timeline"
        startValue = lookupColumn "start"
        endValue = lookupColumn "end"
        attributeLines =
            [ "    " <> label <> ": " <> quotedOrNumeric value <> ","
            | label <- header
            , label `notElem` ["name", "type", "timeline", "start", "end"]
            , let value = lookupColumn label
            , not (T.null value)
            ]

importRelationships :: [Text] -> [(Int, [Text])] -> Either [Diagnostic] Text
importRelationships header rows =
    render <$> traverse renderRow rows
  where
    render blocks = T.unlines blocks
    renderRow (lineNumber, columns)
        | T.null sourceValue || T.null targetValue =
            Left (diag lineNumber "empty source or target")
        | otherwise =
            Right $
                baseRel <> temporalSuffix <> ";"
      where
        lookupColumn label = columnValue header columns label
        sourceValue = lookupColumn "source"
        targetValue = lookupColumn "target"
        labelValue = lookupColumn "label"
        startValue = lookupColumn "start"
        endValue = lookupColumn "end"
        baseRel =
            if T.null labelValue
                then "rel " <> sourceValue <> " --> " <> targetValue
                else "rel " <> sourceValue <> " -[\"" <> labelValue <> "\"]-> " <> targetValue
        temporalSuffix =
            if T.null startValue || T.null endValue
                then ""
                else " @ " <> startValue <> ".." <> endValue

parseCsvFields :: Text -> [Text]
parseCsvFields = finalize . T.foldl' step (False, "", [])
  where
    step (insideQuotes, current, fields) charValue
        | insideQuotes =
            case charValue of
                '"' -> (False, current, fields)
                _ -> (True, T.snoc current charValue, fields)
        | charValue == '"' = (True, current, fields)
        | charValue == ',' = (False, "", fields ++ [trim current])
        | otherwise = (False, T.snoc current charValue, fields)
    finalize (_, current, fields) = fields ++ [trim current]
    trim = T.dropAround isSpace

columnValue :: [Text] -> [Text] -> Text -> Text
columnValue header columns label =
    case elemIndex label header of
        Nothing -> ""
        Just indexValue -> fromMaybe "" (safeIndex indexValue columns)

safeIndex :: Int -> [a] -> Maybe a
safeIndex indexValue values
    | indexValue < 0 = Nothing
    | otherwise =
        case drop indexValue values of
            [] -> Nothing
            value : _ -> Just value

quotedOrNumeric :: Text -> Text
quotedOrNumeric value
    | T.all (\c -> c == '-' || c == '.' || ('0' <= c && c <= '9')) value = value
    | otherwise = "\"" <> value <> "\""

defaultText :: Text -> Text -> Text
defaultText fallback value
    | T.null value = fallback
    | otherwise = value

diag :: Int -> Text -> Diagnostic
diag lineNumber message =
    Diagnostic
        { diagnosticLevel = DiagnosticError
        , diagnosticSource = "import:csv:line:" <> T.pack (show lineNumber)
        , diagnosticMessage = message
        }
