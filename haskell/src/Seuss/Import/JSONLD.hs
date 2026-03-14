{-# LANGUAGE OverloadedStrings #-}

module Seuss.Import.JSONLD
    ( importJsonLdToSeuss
    ) where

import Control.Applicative ((<|>))
import Data.Aeson
import Data.Aeson.Key (Key, fromText, toText)
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Maybe (fromMaybe, mapMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import qualified Data.Vector as Vector
import Seuss.Model.Types

importJsonLdToSeuss :: Text -> Either [Diagnostic] Text
importJsonLdToSeuss input =
    case eitherDecodeStrict' (TE.encodeUtf8 input) of
        Left err ->
            Left [Diagnostic DiagnosticError "import:jsonld" (T.pack err)]
        Right value ->
            case extractObjects value of
                [] ->
                    Left [Diagnostic DiagnosticError "import:jsonld" "no object records found in JSON-LD input"]
                objects ->
                    Right $
                        T.unlines $
                            [ "timeline jsonld_import {"
                            , "    kind: linear,"
                            , "    start: 1900-01-01,"
                            , "    end: 2100-12-31,"
                            , "}"
                            , ""
                            ]
                                ++ concatMap renderObject objects

extractObjects :: Value -> [Object]
extractObjects (Array values) = mapMaybe unwrapObject (Vector.toList values)
extractObjects (Object obj) =
    case KeyMap.lookup "@graph" obj of
        Just (Array values) -> mapMaybe unwrapObject (Vector.toList values)
        _ -> maybe [] pure (unwrapObject (Object obj))
extractObjects _ = []

unwrapObject :: Value -> Maybe Object
unwrapObject (Object obj) = Just obj
unwrapObject _ = Nothing

renderObject :: Object -> [Text]
renderObject obj =
    [ "entity " <> sanitize nameValue <> " : " <> sanitize typeValue <> " {"
    ]
        ++ attributeLines
        ++ [ "    appears_on: " <> timelineValue <> " @ " <> startValue <> ".." <> endValue <> ","
           , "}"
           , ""
           ]
  where
    nameValue = objectText ["name", "@id"] "jsonld_entity" obj
    typeValue = objectText ["type", "@type"] "entity" obj
    timelineValue = objectText ["timeline"] "jsonld_import" obj
    startValue = objectText ["start"] "1900-01-01" obj
    endValue = objectText ["end"] "2100-12-31" obj
    ignored = ["name", "@id", "type", "@type", "timeline", "start", "end", "@context", "@graph"]
    attributeLines =
        [ "    " <> renderedKey <> ": " <> renderJsonValue value <> ","
        | (keyValue, value) <- KeyMap.toList obj
        , let renderedKey = toText keyValue
        , renderedKey `notElem` ignored
        ]

objectText :: [Text] -> Text -> Object -> Text
objectText keys fallback obj =
    fromMaybe fallback $
        foldr
            ( \key acc ->
                acc <|> case KeyMap.lookup (fromStringKey key) obj of
                    Just (String textValue) -> Just textValue
                    Just value -> Just (T.pack (show value))
                    Nothing -> Nothing
            )
            Nothing
            keys

fromStringKey :: Text -> Key
fromStringKey = fromText

renderJsonValue :: Value -> Text
renderJsonValue (String textValue) = "\"" <> textValue <> "\""
renderJsonValue (Number numberValue) = T.pack (show numberValue)
renderJsonValue (Bool boolValue) = if boolValue then "true" else "false"
renderJsonValue Null = "null"
renderJsonValue value = "\"" <> T.pack (show value) <> "\""

sanitize :: Text -> Text
sanitize =
    T.map
        (\c -> if c `elem` [' ', ':', '/'] then '_' else c)
