{-# LANGUAGE OverloadedStrings #-}

module Seuss.Import.GEDCOM
    ( importGedcomToSeuss
    ) where

import Data.List (foldl')
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Model.Types

data GedcomPerson = GedcomPerson
    { gpId :: Text
    , gpName :: Maybe Text
    , gpSex :: Maybe Text
    }

importGedcomToSeuss :: Text -> Either [Diagnostic] Text
importGedcomToSeuss input
    | null persons =
        Left
            [ Diagnostic DiagnosticError "import:gedcom" "no INDI records found in GEDCOM input"
            ]
    | otherwise =
        Right $
            T.unlines $
                [ "timeline gedcom_import {"
                , "    kind: linear,"
                , "    start: 1900-01-01,"
                , "    end: 2100-12-31,"
                , "}"
                , ""
                ]
                    ++ concatMap renderPerson persons
  where
    persons = Map.elems (collectPeople (T.lines input))

collectPeople :: [Text] -> Map Text GedcomPerson
collectPeople = snd . foldl' step (Nothing, Map.empty)
  where
    step (currentId, people) lineValue =
        case T.words (T.strip lineValue) of
            ["0", personId, "INDI"] ->
                let normalizedId = T.dropAround (== '@') personId
                    person =
                        GedcomPerson
                            { gpId = normalizedId
                            , gpName = Nothing
                            , gpSex = Nothing
                            }
                 in (Just normalizedId, Map.insert normalizedId person people)
            ["1", "NAME", rest] ->
                updateCurrent currentId people (\person -> person{gpName = Just (cleanName rest)})
            ("1" : "NAME" : restWords) ->
                updateCurrent currentId people (\person -> person{gpName = Just (cleanName (T.unwords restWords))})
            ["1", "SEX", sexValue] ->
                updateCurrent currentId people (\person -> person{gpSex = Just sexValue})
            _ -> (currentId, people)

updateCurrent :: Maybe Text -> Map Text GedcomPerson -> (GedcomPerson -> GedcomPerson) -> (Maybe Text, Map Text GedcomPerson)
updateCurrent currentId people f =
    case currentId of
        Nothing -> (currentId, people)
        Just ident ->
            let updated = maybe (GedcomPerson ident Nothing Nothing) f (Map.lookup ident people)
             in (currentId, Map.insert ident updated people)

renderPerson :: GedcomPerson -> [Text]
renderPerson person =
    [ "entity " <> entityNameValue <> " : person {"
    ]
        ++ sexLine
        ++ [ "    appears_on: gedcom_import @ 1900-01-01..2100-12-31,"
           , "}"
           , ""
           ]
  where
    entityNameValue = sanitize (maybe (gpId person) id (gpName person))
    sexLine =
        case gpSex person of
            Nothing -> []
            Just value -> ["    sex: \"" <> value <> "\","]

cleanName :: Text -> Text
cleanName = T.replace "/" "" . T.strip

sanitize :: Text -> Text
sanitize =
    T.map
        (\c -> if c `elem` [' ', '-'] then '_' else c)
