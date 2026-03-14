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
            [ renderSection "Timelines" leftTimelines rightTimelines
            , renderSection "Entities" leftEntities rightEntities
            , renderSection "Relationships" leftRelationships rightRelationships
            ]
  where
    leftTimelines = Set.fromList (Map.keys (worldTimelines leftWorld))
    rightTimelines = Set.fromList (Map.keys (worldTimelines rightWorld))
    leftEntities = Set.fromList (Map.keys (worldEntities leftWorld))
    rightEntities = Set.fromList (Map.keys (worldEntities rightWorld))
    leftRelationships = Set.fromList (map renderRelationship (worldRelationships leftWorld))
    rightRelationships = Set.fromList (map renderRelationship (worldRelationships rightWorld))

renderSection :: Text -> Set Text -> Set Text -> [Text]
renderSection title leftSet rightSet =
    [ title <> ":"
    ]
        ++ renderDelta "+ only in right" (Set.toList (rightSet `Set.difference` leftSet))
        ++ renderDelta "- only in left" (Set.toList (leftSet `Set.difference` rightSet))

renderDelta :: Text -> [Text] -> [Text]
renderDelta _ [] = ["  (no differences)"]
renderDelta label values =
    map (\value -> "  " <> label <> " " <> value) (sort values)

renderRelationship :: Relationship -> Text
renderRelationship relationship =
    relSource relationship
        <> " "
        <> maybe "--" (\label -> "-[" <> label <> "]->") (relLabel relationship)
        <> " "
        <> relTarget relationship
