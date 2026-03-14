{-# LANGUAGE OverloadedStrings #-}

module Seuss.Core.Eval
    ( evalProgram
    ) where

import Control.Monad (foldM, traverse_, unless)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe, isJust)
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Lang.AST
import Seuss.Model.Types

data EvalState = EvalState
    { evalWorld :: World
    , evalEnv :: Map Text Value
    , evalFunctions :: Map Text FnDecl
    , evalClosures :: Map Integer ClosureDef
    , evalNextClosureId :: Integer
    , evalFunctionDepth :: Int
    , evalReturnValue :: Maybe Value
    }

data ClosureDef = ClosureDef
    { closureParams :: [(Text, Text)]
    , closureBody :: Expr
    , closureCapturedEnv :: Map Text Value
    }

maxWhileIterations :: Integer
maxWhileIterations = 10000

evalProgram :: Program -> Either Diagnostic World
evalProgram (Program statements) =
    evalWorld <$> foldM evalStmt (EvalState emptyWorld Map.empty Map.empty Map.empty 0 0 Nothing) statements

evalStmt :: EvalState -> Stmt -> Either Diagnostic EvalState
evalStmt state statement =
    case evalReturnValue state of
        Just _ -> pure state
        Nothing ->
            case statement of
                StmtType decl -> do
                    rejectDuplicate "type" (typeDeclName decl) (worldTypes (evalWorld state))
                    (state1, metaValues) <- evalExprMap state (typeDeclMeta decl)
                    let world' =
                            (evalWorld state1)
                                { worldTypes =
                                    Map.insert
                                        (typeDeclName decl)
                                        TypeDef
                                            { typeName = typeDeclName decl
                                            , typeParent = typeDeclParent decl
                                            , typeFields = typeDeclFields decl
                                            , typeMeta = metaValues
                                            }
                                        (worldTypes (evalWorld state1))
                                }
                    pure state1{evalWorld = world'}
                StmtTimeline decl -> do
                    rejectDuplicate "timeline" (timelineDeclName decl) (worldTimelines (evalWorld state))
                    (state1, startValue) <- exprToTimePoint state (timelineDeclStart decl)
                    (state2, endValue) <- exprToTimePoint state1 (timelineDeclEnd decl)
                    (state3, loopCountValue) <- evalOptionalInteger state2 (timelineDeclLoopCount decl)
                    (state4, forkValue) <- evalOptionalTimelineRef state3 (timelineDeclForkFrom decl)
                    (state5, mergeValue) <- evalOptionalTimelineRef state4 (timelineDeclMergeInto decl)
                    let world' =
                            (evalWorld state5)
                                { worldTimelines =
                                    Map.insert
                                        (timelineDeclName decl)
                                        Timeline
                                            { timelineName = timelineDeclName decl
                                            , timelineKind = timelineDeclKind decl
                                            , timelineStart = startValue
                                            , timelineEnd = endValue
                                            , timelineParent = timelineDeclParent decl
                                            , timelineForkFrom = forkValue
                                            , timelineMergeInto = mergeValue
                                            , timelineLoopCount = loopCountValue
                                            }
                                        (worldTimelines (evalWorld state5))
                                }
                    pure state5{evalWorld = world'}
                StmtEntity decl -> do
                    rejectDuplicate "entity" (entityDeclName decl) (worldEntities (evalWorld state))
                    (state1, fieldValues) <- evalExprMap state (entityDeclFields decl)
                    (state2, appearances) <- evalAppearances state1 (entityDeclAppearances decl)
                    let world' =
                            (evalWorld state2)
                                { worldEntities =
                                    Map.insert
                                        (entityDeclName decl)
                                        Entity
                                            { entityName = entityDeclName decl
                                            , entityType = maybe "entity" id (entityDeclType decl)
                                            , entityFields = fieldValues
                                            , entityAppearances = appearances
                                            }
                                        (worldEntities (evalWorld state2))
                                }
                    pure state2{evalWorld = world'}
                StmtRelationship decl -> do
                    (state1, scope) <-
                        case relationshipDeclTemporalScope decl of
                            Nothing -> pure (state, Nothing)
                            Just (startExpr, endExpr) -> do
                                (state', startValue) <- exprToTimePoint state startExpr
                                (state'', endValue) <- exprToTimePoint state' endExpr
                                pure (state'', Just (TimeRange startValue endValue))
                    let world' =
                            (evalWorld state1)
                                { worldRelationships =
                                    worldRelationships (evalWorld state1)
                                        ++ [ Relationship
                                                { relSource = relationshipDeclSource decl
                                                , relLabel = relationshipDeclLabel decl
                                                , relTarget = relationshipDeclTarget decl
                                                , relDirected = relationshipDeclDirected decl
                                                , relTemporalScope = scope
                                                }
                                           ]
                                }
                    pure state1{evalWorld = world'}
                StmtImport _ ->
                    pure state
                StmtLet decl -> do
                    (state1, value) <- evalExpr state (letValue decl)
                    maybe (pure ()) (assertTypeMatches state1 value) (letTypeAnnotation decl)
                    pure state1{evalEnv = Map.insert (letName decl) value (evalEnv state1)}
                StmtAssign name expr ->
                    if Map.member name (evalEnv state)
                        then do
                            (state1, value) <- evalExpr state expr
                            pure state1{evalEnv = Map.insert name value (evalEnv state1)}
                        else
                            Left $
                                Diagnostic
                                    { diagnosticLevel = DiagnosticError
                                    , diagnosticSource = "evaluator"
                                    , diagnosticMessage = "cannot assign to undefined variable: " <> name
                                    }
                StmtFor decl ->
                    evalForLoop state decl
                StmtRepeat decl ->
                    evalRepeatLoop state decl
                StmtWhile decl ->
                    evalWhileLoop state decl
                StmtFunction decl -> do
                    let world' =
                            (evalWorld state)
                                { worldFunctions =
                                    Map.insert
                                        (fnName decl)
                                        FunctionSig
                                            { functionName = fnName decl
                                            , functionParams = fnParams decl
                                            , functionReturnType = fnReturnType decl
                                            }
                                        (worldFunctions (evalWorld state))
                                }
                    pure
                        state
                            { evalWorld = world'
                            , evalFunctions = Map.insert (fnName decl) decl (evalFunctions state)
                            }
                StmtIf decl -> do
                    (state1, conditionValue) <- evalExpr state (ifCondition decl)
                    case conditionValue of
                        VBool True -> foldM evalStmt state1 (ifThenBlock decl)
                        VBool False -> evalElseBranches state1 (ifElseIfBlocks decl) (ifElseBlock decl)
                        _ ->
                            Left $
                                Diagnostic
                                    { diagnosticLevel = DiagnosticError
                                    , diagnosticSource = "evaluator"
                                    , diagnosticMessage = "if condition must evaluate to a boolean"
                                    }
                StmtMatch decl ->
                    evalMatch state decl
                StmtReturn maybeExpr ->
                    if evalFunctionDepth state <= 0
                        then
                            Left $
                                Diagnostic
                                    { diagnosticLevel = DiagnosticError
                                    , diagnosticSource = "evaluator"
                                    , diagnosticMessage = "return can only be used inside a function"
                                    }
                        else do
                            (state1, returnValue) <-
                                case maybeExpr of
                                    Nothing -> pure (state, VNull)
                                    Just expr -> evalExpr state expr
                            pure state1{evalReturnValue = Just returnValue}
                StmtExpr expr ->
                    fst <$> evalExpr state expr

evalExpr :: EvalState -> Expr -> Either Diagnostic (EvalState, Value)
evalExpr state (ExprValue value) = Right (state, value)
evalExpr state (ExprIdent name) =
    case Map.lookup name (evalEnv state) of
        Just value -> Right (state, value)
        Nothing ->
            case findEntity name (evalWorld state) of
                Just _ -> Right (state, VEntityRef name)
                Nothing ->
                    case findTimeline name (evalWorld state) of
                        Just _ -> Right (state, VTimelineRef name)
                        Nothing -> Right (state, VString name)
evalExpr state (ExprList exprs) = do
    (nextState, values) <- evalExprList state exprs
    pure (nextState, VList values)
evalExpr state (ExprRange startExpr endExpr) = do
    (state1, startValue) <- evalExpr state startExpr
    (state2, endValue) <- evalExpr state1 endExpr
    case (startValue, endValue) of
        (VInt startInt, VInt endInt) ->
            pure
                ( state2
                , VList $
                    map VInt $
                        if startInt <= endInt
                            then [startInt .. endInt]
                            else reverse [endInt .. startInt]
                )
        _ ->
            pure (state2, VList [startValue, endValue])
evalExpr state (ExprIndex objectExpr indexExpr) = do
    (state1, objectValue) <- evalExpr state objectExpr
    (state2, indexValue) <- evalExpr state1 indexExpr
    case indexValue of
        VInt indexInt
            | indexInt < 0 ->
                Left $
                    Diagnostic
                        { diagnosticLevel = DiagnosticError
                        , diagnosticSource = "evaluator"
                        , diagnosticMessage = "index must be non-negative"
                        }
            | otherwise ->
                do
                    indexedValue <- evalIndex objectValue (fromInteger indexInt)
                    pure (state2, indexedValue)
        _ ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "index expression must evaluate to an integer"
                    }
evalExpr state (ExprField objectExpr fieldName) = do
    (state1, objectValue) <- evalExpr state objectExpr
    fieldValue <- evalFieldAccess state1 objectValue fieldName
    pure (state1, fieldValue)
evalExpr state (ExprCall calleeExpr argExprs) =
    evalCall state calleeExpr argExprs
evalExpr state (ExprClosure params bodyExpr) =
    let closureId = evalNextClosureId state
        closureDef =
            ClosureDef
                { closureParams = params
                , closureBody = bodyExpr
                , closureCapturedEnv = evalEnv state
                }
        nextState =
            state
                { evalClosures = Map.insert closureId closureDef (evalClosures state)
                , evalNextClosureId = closureId + 1
                }
     in Right (nextState, VClosureRef closureId)
evalExpr state (ExprBinary op lhs rhs) = do
    (state1, leftValue) <- evalExpr state lhs
    (state2, rightValue) <- evalExpr state1 rhs
    resultValue <- evalBinary op leftValue rightValue
    pure (state2, resultValue)

evalBinary :: BinaryOp -> Value -> Value -> Either Diagnostic Value
evalBinary OpAdd (VInt leftValue) (VInt rightValue) = Right (VInt (leftValue + rightValue))
evalBinary OpSub (VInt leftValue) (VInt rightValue) = Right (VInt (leftValue - rightValue))
evalBinary OpGt (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue > rightValue))
evalBinary OpGt (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue > rightValue))
evalBinary OpLt (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue < rightValue))
evalBinary OpLt (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue < rightValue))
evalBinary OpGte (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue >= rightValue))
evalBinary OpGte (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue >= rightValue))
evalBinary OpLte (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue <= rightValue))
evalBinary OpLte (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue <= rightValue))
evalBinary OpEq leftValue rightValue = Right (VBool (leftValue == rightValue))
evalBinary OpNeq leftValue rightValue = Right (VBool (leftValue /= rightValue))
evalBinary OpAnd (VBool leftValue) (VBool rightValue) = Right (VBool (leftValue && rightValue))
evalBinary OpOr (VBool leftValue) (VBool rightValue) = Right (VBool (leftValue || rightValue))
evalBinary op leftValue rightValue =
    Left $
        Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "evaluator"
            , diagnosticMessage =
                "unsupported operands for "
                    <> T.pack (show op)
                    <> ": "
                    <> T.pack (show leftValue)
                    <> " and "
                    <> T.pack (show rightValue)
            }

evalIndex :: Value -> Int -> Either Diagnostic Value
evalIndex (VList values) indexValue
    | indexValue < length values = Right (values !! indexValue)
    | otherwise = Left (indexOutOfBounds "list" indexValue (length values))
evalIndex (VString textValue) indexValue
    | indexValue < T.length textValue =
        Right (VString (T.singleton (T.index textValue indexValue)))
    | otherwise =
        Left (indexOutOfBounds "string" indexValue (T.length textValue))
evalIndex value _ =
    Left $
        Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "evaluator"
            , diagnosticMessage = "cannot index into value " <> T.pack (show value)
            }

indexOutOfBounds :: Text -> Int -> Int -> Diagnostic
indexOutOfBounds targetName indexValue targetLength =
    Diagnostic
        { diagnosticLevel = DiagnosticError
        , diagnosticSource = "evaluator"
        , diagnosticMessage =
            "index "
                <> T.pack (show indexValue)
                <> " is out of bounds for "
                <> targetName
                <> " of length "
                <> T.pack (show targetLength)
        }

evalCall :: EvalState -> Expr -> [Expr] -> Either Diagnostic (EvalState, Value)
evalCall state calleeExpr argExprs = do
    (state1, calleeValue) <- evalExpr state calleeExpr
    (state2, argValues) <- evalExprList state1 argExprs
    case calleeValue of
        VClosureRef closureId ->
            callClosure state2 closureId argValues
        _ ->
            case calleeExpr of
                ExprIdent name ->
                    case Map.lookup name (evalFunctions state2) of
                        Just fnDecl ->
                            callNamedFunction state2 name fnDecl argValues
                        Nothing ->
                            case evalBuiltin state2 name argValues of
                                Just builtinValue ->
                                    pure (state2, builtinValue)
                                Nothing ->
                                    undefinedFunction name
                _ ->
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage = "only named functions and closure values are callable in the current Haskell rewrite"
                            }

callNamedFunction :: EvalState -> Text -> FnDecl -> [Value] -> Either Diagnostic (EvalState, Value)
callNamedFunction state name fnDecl argValues =
    if length argValues /= length (fnParams fnDecl)
        then
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage =
                        "function "
                            <> name
                            <> " expected "
                            <> T.pack (show (length (fnParams fnDecl)))
                            <> " arguments but got "
                            <> T.pack (show (length argValues))
                    }
        else do
            traverse_ (uncurry (assertTypeMatches state)) (zip argValues (map snd (fnParams fnDecl)))
            let savedEnv = evalEnv state
                savedReturn = evalReturnValue state
                paramBindings = Map.fromList (zip (map fst (fnParams fnDecl)) argValues)
                callState =
                    state
                        { evalEnv = paramBindings `Map.union` savedEnv
                        , evalFunctionDepth = evalFunctionDepth state + 1
                        , evalReturnValue = Nothing
                        }
            (resultState, resultValue) <- evalBlockWithResult callState (fnBody fnDecl)
            let finalValue = fromMaybe resultValue (evalReturnValue resultState)
            maybe (pure ()) (assertTypeMatches resultState finalValue) (fnReturnType fnDecl)
            pure
                ( resultState
                    { evalEnv = savedEnv
                    , evalFunctionDepth = evalFunctionDepth state
                    , evalReturnValue = savedReturn
                    }
                , finalValue
                )

callClosure :: EvalState -> Integer -> [Value] -> Either Diagnostic (EvalState, Value)
callClosure state closureId argValues =
    case Map.lookup closureId (evalClosures state) of
        Nothing ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "unknown closure reference: " <> T.pack (show closureId)
                    }
        Just closureDef ->
            if length argValues /= length (closureParams closureDef)
                then
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage =
                                "closure expected "
                                    <> T.pack (show (length (closureParams closureDef)))
                                    <> " arguments but got "
                                    <> T.pack (show (length argValues))
                            }
                else do
                    let savedEnv = evalEnv state
                        paramBindings = Map.fromList (zip (map fst (closureParams closureDef)) argValues)
                        callState =
                            state
                                { evalEnv = paramBindings `Map.union` closureCapturedEnv closureDef
                                , evalFunctionDepth = evalFunctionDepth state + 1
                                , evalReturnValue = Nothing
                                }
                    (resultState, resultValue) <- evalExpr callState (closureBody closureDef)
                    pure
                        ( resultState
                            { evalEnv = savedEnv
                            , evalFunctionDepth = evalFunctionDepth state
                            , evalReturnValue = evalReturnValue state
                            }
                        , resultValue
                        )

evalBuiltin :: EvalState -> Text -> [Value] -> Maybe Value
evalBuiltin state name args =
    case name of
        "len" ->
            case args of
                [VList items] -> Just (VInt (toInteger (length items)))
                [VString textValue] -> Just (VInt (toInteger (T.length textValue)))
                _ -> Nothing
        "before" ->
            case args of
                [leftValue, rightValue] -> VBool <$> ((<) <$> valueToOrdinal leftValue <*> valueToOrdinal rightValue)
                _ -> Nothing
        "after" ->
            case args of
                [leftValue, rightValue] -> VBool <$> ((>) <$> valueToOrdinal leftValue <*> valueToOrdinal rightValue)
                _ -> Nothing
        "type_of" ->
            case args of
                [VEntityRef entityName] ->
                    VString . entityType <$> findEntity entityName (evalWorld state)
                [VString entityName] ->
                    VString . entityType <$> findEntity entityName (evalWorld state)
                _ -> Nothing
        _ -> Nothing

valueToOrdinal :: Value -> Maybe Integer
valueToOrdinal (VInt value) = Just value
valueToOrdinal (VDate day) = Just (timePointOrdinal (TimeDate day))
valueToOrdinal _ = Nothing

assertTypeMatches :: EvalState -> Value -> Text -> Either Diagnostic ()
assertTypeMatches state value expectedType
    | valueMatchesType state value expectedType = pure ()
    | otherwise =
        Left $
            Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "evaluator"
                , diagnosticMessage =
                    "type mismatch: expected "
                        <> expectedType
                        <> " but got "
                        <> renderValueType state value
                }

valueMatchesType :: EvalState -> Value -> Text -> Bool
valueMatchesType _ VNull _ = True
valueMatchesType _ (VInt _) "int" = True
valueMatchesType _ (VString _) "string" = True
valueMatchesType _ (VBool _) "bool" = True
valueMatchesType _ (VDate _) "date" = True
valueMatchesType _ (VList _) "list" = True
valueMatchesType _ (VEntityRef _) "entity" = True
valueMatchesType state (VEntityRef entityName) expectedType =
    case findEntity entityName (evalWorld state) of
        Nothing -> False
        Just entity ->
            entityType entity == expectedType
                || hasTypeAncestor (evalWorld state) (entityType entity) expectedType
valueMatchesType _ (VTimelineRef _) "timeline" = True
valueMatchesType _ (VClosureRef _) "closure" = True
valueMatchesType _ _ _ = False

renderValueType :: EvalState -> Value -> Text
renderValueType _ VNull = "null"
renderValueType _ (VInt _) = "int"
renderValueType _ (VString _) = "string"
renderValueType _ (VBool _) = "bool"
renderValueType _ (VDate _) = "date"
renderValueType _ (VList _) = "list"
renderValueType state (VEntityRef entityName) =
    maybe "entity" entityType (findEntity entityName (evalWorld state))
renderValueType _ (VTimelineRef _) = "timeline"
renderValueType _ (VClosureRef _) = "closure"

hasTypeAncestor :: World -> Text -> Text -> Bool
hasTypeAncestor worldValue currentType expectedType =
    currentType == expectedType
        || case Map.lookup currentType (worldTypes worldValue) of
            Nothing -> False
            Just typeDef ->
                case typeParent typeDef of
                    Nothing -> False
                    Just parentName -> hasTypeAncestor worldValue parentName expectedType

undefinedFunction :: Text -> Either Diagnostic a
undefinedFunction name =
    Left $
        Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "evaluator"
            , diagnosticMessage = "undefined function: " <> name
            }

evalFieldAccess :: EvalState -> Value -> Text -> Either Diagnostic Value
evalFieldAccess state objectValue fieldName =
    case objectValue of
        VEntityRef name ->
            case findEntity name (evalWorld state) of
                Just entity ->
                    case fieldName of
                        "name" -> Right (VString (entityName entity))
                        "type" -> Right (VString (entityType entity))
                        _ ->
                            maybe
                                ( maybe
                                    (unknownField "entity" fieldName)
                                    Right
                                    (lookupTypeMetaValue (evalWorld state) (entityType entity) fieldName)
                                )
                                Right
                                (Map.lookup fieldName (entityFields entity))
                Nothing ->
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage = "unknown entity reference: " <> name
                            }
        VTimelineRef name ->
            case findTimeline name (evalWorld state) of
                Just timeline ->
                    case fieldName of
                        "name" -> Right (VString (timelineName timeline))
                        "kind" -> Right (VString (timelineKindText (timelineKind timeline)))
                        "start" -> Right (timePointToValue (timelineStart timeline))
                        "end" -> Right (timePointToValue (timelineEnd timeline))
                        "parent" -> Right (maybe VNull VString (timelineParent timeline))
                        "loop_count" -> Right (maybe VNull VInt (timelineLoopCount timeline))
                        _ -> unknownField "timeline" fieldName
                Nothing ->
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage = "unknown timeline reference: " <> name
                            }
        _ ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage =
                        "cannot access field "
                            <> fieldName
                            <> " on value "
                            <> T.pack (show objectValue)
                    }

timelineKindText :: TimelineKind -> Text
timelineKindText TimelineLinear = "linear"
timelineKindText TimelineBranch = "branch"
timelineKindText TimelineParallel = "parallel"
timelineKindText TimelineLoop = "loop"

timePointToValue :: TimePoint -> Value
timePointToValue (TimeDate day) = VDate day
timePointToValue (TimeOrdinal value) = VInt value

unknownField :: Text -> Text -> Either Diagnostic a
unknownField targetKind fieldName =
    Left $
        Diagnostic
            { diagnosticLevel = DiagnosticError
            , diagnosticSource = "evaluator"
            , diagnosticMessage = "unknown " <> targetKind <> " field: " <> fieldName
            }

lookupTypeMetaValue :: World -> Text -> Text -> Maybe Value
lookupTypeMetaValue worldValue typeNameValue fieldName =
    case Map.lookup typeNameValue (worldTypes worldValue) of
        Nothing -> Nothing
        Just typeDef ->
            case Map.lookup fieldName (typeMeta typeDef) of
                Just metaValue -> Just metaValue
                Nothing ->
                    case typeParent typeDef of
                        Nothing -> Nothing
                        Just parentName -> lookupTypeMetaValue worldValue parentName fieldName

evalExprList :: EvalState -> [Expr] -> Either Diagnostic (EvalState, [Value])
evalExprList state exprs =
    foldM
        ( \(currentState, values) expr -> do
            (nextState, value) <- evalExpr currentState expr
            pure (nextState, values ++ [value])
        )
        (state, [])
        exprs

evalExprMap :: EvalState -> Map Text Expr -> Either Diagnostic (EvalState, Map Text Value)
evalExprMap state exprs = do
    (nextState, values) <-
        foldM
            ( \(currentState, entries) (fieldName, expr) -> do
                (updatedState, value) <- evalExpr currentState expr
                pure (updatedState, entries ++ [(fieldName, value)])
            )
            (state, [])
            (Map.toAscList exprs)
    pure (nextState, Map.fromList values)

evalAppearances :: EvalState -> [AppearanceDecl] -> Either Diagnostic (EvalState, [Appearance])
evalAppearances state appearanceDecls =
    foldM
        ( \(currentState, appearances) appearance -> do
            (state1, startValue) <- exprToTimePoint currentState (appearanceDeclStart appearance)
            (state2, endValue) <- exprToTimePoint state1 (appearanceDeclEnd appearance)
            pure
                ( state2
                , appearances
                    ++ [ Appearance
                            (appearanceDeclTimeline appearance)
                            (TimeRange startValue endValue)
                       ]
                )
        )
        (state, [])
        appearanceDecls

evalOptionalInteger :: EvalState -> Maybe Expr -> Either Diagnostic (EvalState, Maybe Integer)
evalOptionalInteger state Nothing = pure (state, Nothing)
evalOptionalInteger state (Just expr) = do
    (nextState, value) <- exprToInteger state expr
    pure (nextState, Just value)

evalOptionalTimelineRef :: EvalState -> Maybe (Text, Expr) -> Either Diagnostic (EvalState, Maybe (Text, TimePoint))
evalOptionalTimelineRef state Nothing = pure (state, Nothing)
evalOptionalTimelineRef state (Just (name, expr)) = do
    (nextState, point) <- exprToTimePoint state expr
    pure (nextState, Just (name, point))

evalBlockWithResult :: EvalState -> [Stmt] -> Either Diagnostic (EvalState, Value)
evalBlockWithResult state statements =
    foldM
        ( \(currentState, _) stmt ->
            case evalReturnValue currentState of
                Just returnValue -> pure (currentState, returnValue)
                Nothing -> evalStmtResult currentState stmt
        )
        (state, VNull)
        statements

evalStmtResult :: EvalState -> Stmt -> Either Diagnostic (EvalState, Value)
evalStmtResult state (StmtReturn maybeExpr) = do
    nextState <- evalStmt state (StmtReturn maybeExpr)
    pure (nextState, fromMaybe VNull (evalReturnValue nextState))
evalStmtResult state (StmtExpr expr) = evalExpr state expr
evalStmtResult state stmt = do
    nextState <- evalStmt state stmt
    pure (nextState, VNull)

exprToTimePoint :: EvalState -> Expr -> Either Diagnostic (EvalState, TimePoint)
exprToTimePoint state expr = do
    (nextState, value) <- evalExpr state expr
    case timePointFromValue value of
        Left message ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = message
                    }
        Right point -> Right (nextState, point)

exprToInteger :: EvalState -> Expr -> Either Diagnostic (EvalState, Integer)
exprToInteger state expr = do
    (nextState, value) <- evalExpr state expr
    case value of
        VInt intValue -> Right (nextState, intValue)
        _ ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "expected an integer expression"
                    }

rejectDuplicate :: Text -> Text -> Map Text a -> Either Diagnostic ()
rejectDuplicate kind name entries =
    unless (Map.notMember name entries) $
        Left $
            Diagnostic
                { diagnosticLevel = DiagnosticError
                , diagnosticSource = "evaluator"
                , diagnosticMessage = "duplicate " <> kind <> ": " <> name
                }

evalElseBranches :: EvalState -> [(Expr, [Stmt])] -> Maybe [Stmt] -> Either Diagnostic EvalState
evalElseBranches state [] Nothing = pure state
evalElseBranches state [] (Just elseBlock) = foldM evalStmt state elseBlock
evalElseBranches state ((conditionExpr, branchBody) : rest) elseBlock = do
    (state1, conditionValue) <- evalExpr state conditionExpr
    case conditionValue of
        VBool True -> foldM evalStmt state1 branchBody
        VBool False -> evalElseBranches state1 rest elseBlock
        _ ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "else-if condition must evaluate to a boolean"
                    }

evalMatch :: EvalState -> MatchDecl -> Either Diagnostic EvalState
evalMatch state decl = do
    (state1, subjectValue) <- evalExpr state (matchSubject decl)
    evalMatchArms state1 subjectValue (matchArms decl)

evalMatchArms :: EvalState -> Value -> [MatchArm] -> Either Diagnostic EvalState
evalMatchArms state _ [] = pure state
evalMatchArms state subjectValue (arm : remainingArms)
    | matchPatternMatches (matchArmPattern arm) subjectValue =
        evalMatchArm state subjectValue arm
    | otherwise =
        evalMatchArms state subjectValue remainingArms

evalMatchArm :: EvalState -> Value -> MatchArm -> Either Diagnostic EvalState
evalMatchArm state subjectValue arm =
    case matchArmPattern arm of
        MatchPatternBind name -> do
            let previousBinding = Map.lookup name (evalEnv state)
                scopedState =
                    state
                        { evalEnv =
                            Map.insert name subjectValue (evalEnv state)
                        }
            matchedState <- foldM evalStmt scopedState (matchArmBody arm)
            pure matchedState{evalEnv = restoreBinding previousBinding name (evalEnv matchedState)}
        _ ->
            foldM evalStmt state (matchArmBody arm)

matchPatternMatches :: MatchPattern -> Value -> Bool
matchPatternMatches MatchPatternWildcard _ = True
matchPatternMatches (MatchPatternValue patternValue) subjectValue = patternValue == subjectValue
matchPatternMatches (MatchPatternBind _) _ = True

evalForLoop :: EvalState -> ForDecl -> Either Diagnostic EvalState
evalForLoop state decl = do
    (state1, values) <- evalForIterable state (forIterable decl)
    let previousBinding = Map.lookup (forVar decl) (evalEnv state1)
    iteratedState <-
        foldM
            ( \currentState value ->
                case evalReturnValue currentState of
                    Just _ -> pure currentState
                    Nothing -> do
                        let scopedState =
                                currentState
                                    { evalEnv =
                                        Map.insert (forVar decl) value (evalEnv currentState)
                                    }
                        foldM evalStmt scopedState (forBody decl)
            )
            state1
            values
    pure iteratedState{evalEnv = restoreBinding previousBinding (forVar decl) (evalEnv iteratedState)}

evalForIterable :: EvalState -> ForIterable -> Either Diagnostic (EvalState, [Value])
evalForIterable state iterable =
    case iterable of
        ForRange startExpr endExpr -> do
            (state1, startValue) <- exprToInteger state startExpr
            (state2, endValue) <- exprToInteger state1 endExpr
            pure
                ( state2
                , map VInt $
                    if startValue <= endValue
                        then [startValue .. endValue]
                        else reverse [endValue .. startValue]
                )
        ForList exprs ->
            evalExprList state exprs
        ForExpr expr -> do
            (state1, value) <- evalExpr state expr
            case value of
                VList values -> pure (state1, values)
                _ -> pure (state1, [value])

restoreBinding :: Maybe Value -> Text -> Map Text Value -> Map Text Value
restoreBinding Nothing name env = Map.delete name env
restoreBinding (Just value) name env = Map.insert name value env

evalRepeatLoop :: EvalState -> RepeatDecl -> Either Diagnostic EvalState
evalRepeatLoop state decl = do
    (state1, countValue) <- exprToInteger state (repeatCount decl)
    if countValue < 0
        then
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "repeat count must be non-negative"
                    }
        else
            foldM
                ( \currentState _ ->
                    case evalReturnValue currentState of
                        Just _ -> pure currentState
                        Nothing -> foldM evalStmt currentState (repeatBody decl)
                )
                state1
                [1 .. countValue]

evalWhileLoop :: EvalState -> WhileDecl -> Either Diagnostic EvalState
evalWhileLoop = go 0
  where
    go iterations state decl
        | isJust (evalReturnValue state) = pure state
        | iterations >= maxWhileIterations =
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "while loop exceeded the maximum iteration limit"
                    }
        | otherwise = do
            (state1, conditionValue) <- evalExpr state (whileCondition decl)
            case conditionValue of
                VBool True -> do
                    steppedState <- foldM evalStmt state1 (whileBody decl)
                    go (iterations + 1) steppedState decl
                VBool False -> pure state
                _ ->
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage = "while condition must evaluate to a boolean"
                            }
