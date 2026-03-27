{-# LANGUAGE OverloadedStrings #-}

module Seuss.Core.Validation
    ( validateWorld
    ) where

import qualified Data.Map.Strict as Map
import Data.Maybe (isNothing)
import qualified Data.Set as Set
import Data.Text (Text)
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
            ++ requiredFieldDiagnostics entity
            ++ fieldTypeDiagnostics entity
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
    requiredFieldDiagnostics entity =
        [ Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "validation"
            , diagnosticMessage =
                "entity "
                    <> entityName entity
                    <> " is missing required field "
                    <> typeFieldName fieldDef
                    <> " for type "
                    <> entityType entity
            }
        | fieldDef <- resolvedTypeFields entity
        , not (typeFieldOptional fieldDef)
        , Map.notMember (typeFieldName fieldDef) (entityFields entity)
        ]
    fieldTypeDiagnostics entity =
        [ Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "validation"
            , diagnosticMessage =
                "entity "
                    <> entityName entity
                    <> " field "
                    <> fieldName
                    <> " does not match declared type "
                    <> typeFieldType fieldDef
            }
        | fieldDef <- resolvedTypeFields entity
        , let fieldName = typeFieldName fieldDef
        , Just fieldValue <- [Map.lookup fieldName (entityFields entity)]
        , not (valueMatchesDeclaredType world fieldValue (typeFieldType fieldDef))
        ]
    resolvedTypeFields entity
        | Set.member (entityType entity) builtInTypes = []
        | otherwise =
            maybe [] (Map.elems . flattenTypeFields world) (Map.lookup (entityType entity) definedTypes)
    appearanceDiagnostics entity appearance =
        timelineDiagnostics
            ++ rangeDiagnostics
            ++ timelineBoundsDiagnostics
      where
        referencedTimeline = findTimeline (appearanceTimeline appearance) world
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
        timelineBoundsDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage =
                    "entity "
                        <> entityName entity
                        <> " has an appearance outside the bounds of timeline "
                        <> appearanceTimeline appearance
                }
            | Just timeline <- [referencedTimeline]
            , let rangeValue = appearanceRange appearance
            , timePointOrdinal (rangeStart rangeValue) < timePointOrdinal (timelineStart timeline)
                || timePointOrdinal (rangeEnd rangeValue) > timePointOrdinal (timelineEnd timeline)
            ]

validateRelationships :: World -> [Diagnostic]
validateRelationships world =
    concatMap validateRelationship (worldRelationships world)
  where
    validateRelationship relationship =
        sourceDiagnostics
            ++ targetDiagnostics
            ++ temporalScopeDiagnostics
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
        temporalScopeDiagnostics =
            [ Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "validation"
                , diagnosticMessage =
                    "relationship temporal scope has start after end: "
                        <> relSource relationship
                        <> " -> "
                        <> relTarget relationship
                }
            | Just rangeValue <- [relTemporalScope relationship]
            , timePointOrdinal (rangeStart rangeValue) > timePointOrdinal (rangeEnd rangeValue)
            ]

flattenTypeFields :: World -> TypeDef -> Map.Map Text TypeField
flattenTypeFields world typeDef =
    ownFields `Map.union` inheritedFields
  where
    inheritedFields =
        case typeParent typeDef >>= (`Map.lookup` worldTypes world) of
            Nothing -> Map.empty
            Just parentType -> flattenTypeFields world parentType
    ownFields =
        Map.fromList
            [ (typeFieldName fieldDef, fieldDef)
            | fieldDef <- typeFields typeDef
            ]

valueMatchesDeclaredType :: World -> Value -> Text -> Bool
valueMatchesDeclaredType _ VNull _ = True
valueMatchesDeclaredType _ (VInt _) "int" = True
valueMatchesDeclaredType _ (VString _) "string" = True
valueMatchesDeclaredType _ (VBool _) "bool" = True
valueMatchesDeclaredType _ (VDate _) "date" = True
valueMatchesDeclaredType _ (VList _) "list" = True
valueMatchesDeclaredType _ (VTimelineRef _) "timeline" = True
valueMatchesDeclaredType _ (VClosureRef _) "closure" = True
valueMatchesDeclaredType _ (VEntityRef _) "entity" = True
valueMatchesDeclaredType world (VEntityRef referencedEntity) expectedType =
    case findEntity referencedEntity world of
        Nothing -> False
        Just entity ->
            entityType entity == expectedType
                || entityTypeInheritsFrom world (entityType entity) expectedType
valueMatchesDeclaredType _ _ _ = False

entityTypeInheritsFrom :: World -> Text -> Text -> Bool
entityTypeInheritsFrom world actualType expectedType
    | actualType == expectedType = True
    | otherwise =
        case Map.lookup actualType (worldTypes world) >>= typeParent of
            Nothing -> False
            Just parentType -> entityTypeInheritsFrom world parentType expectedType
