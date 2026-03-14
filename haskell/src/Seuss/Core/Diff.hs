{-# LANGUAGE OverloadedStrings #-}

module Seuss.Core.Diff
    ( diffWorlds
    ) where

import Data.List (sort)
import qualified Data.Map.Strict as Map
import Data.Set (Set)
import qualified Data.Set as Set
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Model.Types

diffWorlds :: World -> World -> Text
diffWorlds leftWorld rightWorld =
    T.unlines $
        concat
            [ renderNamedSection "Timelines" (worldTimelines leftWorld) (worldTimelines rightWorld) renderTimeline
            , renderNamedSection "Entities" (worldEntities leftWorld) (worldEntities rightWorld) renderEntity
            , renderSetSection "Relationships" leftRelationships rightRelationships
            ]
  where
    leftRelationships = Set.fromList (map renderRelationshipSummary (worldRelationships leftWorld))
    rightRelationships = Set.fromList (map renderRelationshipSummary (worldRelationships rightWorld))

renderNamedSection :: Text -> Map.Map Text a -> Map.Map Text a -> (a -> Text) -> [Text]
renderNamedSection title leftMap rightMap renderValue =
    [ title <> ":"
    ]
        ++ renderDelta "+ only in right" addedNames
        ++ renderDelta "- only in left" removedNames
        ++ renderChanged changedEntries
  where
    leftNames = Set.fromList (Map.keys leftMap)
    rightNames = Set.fromList (Map.keys rightMap)
    addedNames = Set.toList (rightNames `Set.difference` leftNames)
    removedNames = Set.toList (leftNames `Set.difference` rightNames)
    changedEntries =
        [ (name, leftSummary, rightSummary)
        | name <- sort (Set.toList (leftNames `Set.intersection` rightNames))
        , let leftSummary = renderValue (leftMap Map.! name)
        , let rightSummary = renderValue (rightMap Map.! name)
        , leftSummary /= rightSummary
        ]

renderSetSection :: Text -> Set Text -> Set Text -> [Text]
renderSetSection title leftSet rightSet =
    [ title <> ":"
    ]
        ++ renderDelta "+ only in right" (Set.toList (rightSet `Set.difference` leftSet))
        ++ renderDelta "- only in left" (Set.toList (leftSet `Set.difference` rightSet))

renderDelta :: Text -> [Text] -> [Text]
renderDelta _ [] = ["  (no differences)"]
renderDelta label values =
    map (\value -> "  " <> label <> " " <> value) (sort values)

renderChanged :: [(Text, Text, Text)] -> [Text]
renderChanged [] = []
renderChanged entries =
    concatMap
        (\(name, leftSummary, rightSummary) -> ["  ~ changed " <> name, "    left: " <> leftSummary, "    right: " <> rightSummary])
        entries

renderTimeline :: Timeline -> Text
renderTimeline timeline =
    T.intercalate
        " | "
        [ "kind=" <> T.pack (show (timelineKind timeline))
        , "start=" <> T.pack (show (timePointOrdinal (timelineStart timeline)))
        , "end=" <> T.pack (show (timePointOrdinal (timelineEnd timeline)))
        , "parent=" <> maybe "-" id (timelineParent timeline)
        , "loop=" <> maybe "-" (T.pack . show) (timelineLoopCount timeline)
        ]

renderEntity :: Entity -> Text
renderEntity entity =
    T.intercalate
        " | "
        [ "type=" <> entityType entity
        , "fields=" <> renderFields (entityFields entity)
        , "appears=" <> renderAppearances (entityAppearances entity)
        ]

renderFields :: Map.Map Text Value -> Text
renderFields fields
    | Map.null fields = "-"
    | otherwise =
        T.intercalate
            ", "
            [ key <> "=" <> T.pack (show value)
            | (key, value) <- Map.toAscList fields
            ]

renderAppearances :: [Appearance] -> Text
renderAppearances [] = "-"
renderAppearances appearances =
    T.intercalate
        ", "
        [ appearanceTimeline appearance
            <> "@"
            <> T.pack (show (timePointOrdinal (rangeStart (appearanceRange appearance))))
            <> ".."
            <> T.pack (show (timePointOrdinal (rangeEnd (appearanceRange appearance))))
        | appearance <- appearances
        ]

renderRelationshipSummary :: Relationship -> Text
renderRelationshipSummary relationship =
    relSource relationship
        <> " "
        <> maybe "--" (\label -> "-[" <> label <> "]->") (relLabel relationship)
        <> " "
        <> relTarget relationship
