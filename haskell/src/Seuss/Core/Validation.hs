{-# LANGUAGE OverloadedStrings #-}

module Seuss.Core.Validation
    ( validateWorld
    ) where

import qualified Data.Map.Strict as Map
import Data.Maybe (isNothing)
import qualified Data.Set as Set
import Seuss.Model.Types

validateWorld :: World -> [Diagnostic]
validateWorld world =
    concat
        [ validateTimelines world
        , validateEntities world
        , validateRelationships world
        ]

validateTimelines :: World -> [Diagnostic]
validateTimelines world =
    concatMap validateTimeline (Map.elems (worldTimelines world))
  where
    validateTimeline timeline =
        timelineBoundsDiagnostics timeline
            ++ maybe [] (timelineRefDiagnostics timeline "parent") (timelineParent timeline)
            ++ maybe [] (forkMergeDiagnostics "fork_from") (timelineForkFrom timeline)
            ++ maybe [] (forkMergeDiagnostics "merge_into") (timelineMergeInto timeline)
    timelineRefDiagnostics timeline label refName =
        [ Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "validation"
            , diagnosticMessage =
                "timeline "
                    <> timelineName timeline
                    <> " references missing "
                    <> label
                    <> " timeline "
                    <> refName
            }
        | isNothing (findTimeline refName world)
        ]
    forkMergeDiagnostics label (refName, _) =
        [ Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "validation"
            , diagnosticMessage = "missing " <> label <> " timeline " <> refName
            }
        | isNothing (findTimeline refName world)
        ]
    timelineBoundsDiagnostics timeline =
        [ Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "validation"
            , diagnosticMessage = "timeline " <> timelineName timeline <> " has start after end"
            }
        | timePointOrdinal (timelineStart timeline) > timePointOrdinal (timelineEnd timeline)
        ]
validateEntities :: World -> [Diagnostic]
validateEntities world =
    concatMap validateEntity (Map.elems (worldEntities world))
  where
    definedTypes = worldTypes world
    validateEntity entity =
        typeDiagnostics entity
            ++ concatMap (appearanceDiagnostics entity) (entityAppearances entity)
    typeDiagnostics entity =
        [ Diagnostic
            { diagnosticLevel = DiagnosticWarning
            , diagnosticSource = "validation"
            , diagnosticMessage = "entity " <> entityName entity <> " uses unknown type " <> entityType entity
            }
        | Set.notMember (entityType entity) builtInTypes
        , Map.notMember (entityType entity) definedTypes
        ]
    appearanceDiagnostics entity appearance =
        timelineDiagnostics
            ++ rangeDiagnostics
      where
        timelineDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage =
                    "entity "
                        <> entityName entity
                        <> " references missing timeline "
                        <> appearanceTimeline appearance
                }
            | isNothing (findTimeline (appearanceTimeline appearance) world)
            ]
        rangeDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage =
                    "entity "
                        <> entityName entity
                        <> " has an appearance range with start after end"
                }
            | let rangeValue = appearanceRange appearance
            , timePointOrdinal (rangeStart rangeValue) > timePointOrdinal (rangeEnd rangeValue)
            ]

validateRelationships :: World -> [Diagnostic]
validateRelationships world =
    concatMap validateRelationship (worldRelationships world)
  where
    validateRelationship relationship =
        sourceDiagnostics
            ++ targetDiagnostics
      where
        sourceDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage = "relationship source not found: " <> relSource relationship
                }
            | isNothing (findEntity (relSource relationship) world)
            ]
        targetDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage = "relationship target not found: " <> relTarget relationship
                }
            | isNothing (findEntity (relTarget relationship) world)
            ]
