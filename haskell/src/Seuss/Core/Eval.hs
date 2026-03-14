{-# LANGUAGE OverloadedStrings #-}

module Seuss.Core.Eval
    ( evalProgram
    ) where

import Control.Monad (foldM, unless)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Lang.AST
import Seuss.Model.Types

data EvalState = EvalState
    { evalWorld :: World
    , evalEnv :: Map Text Value
    }

evalProgram :: Program -> Either Diagnostic World
evalProgram (Program statements) =
    evalWorld <$> foldM evalStmt (EvalState emptyWorld Map.empty) statements

evalStmt :: EvalState -> Stmt -> Either Diagnostic EvalState
evalStmt state statement =
    case statement of
        StmtType decl -> do
            rejectDuplicate "type" (typeDeclName decl) (worldTypes (evalWorld state))
            let world' =
                    (evalWorld state)
                        { worldTypes =
                            Map.insert
                                (typeDeclName decl)
                                TypeDef
                                    { typeName = typeDeclName decl
                                    , typeParent = typeDeclParent decl
                                    , typeFields = typeDeclFields decl
                                    }
                                (worldTypes (evalWorld state))
                        }
            pure state{evalWorld = world'}
        StmtTimeline decl -> do
            rejectDuplicate "timeline" (timelineDeclName decl) (worldTimelines (evalWorld state))
            startValue <- exprToTimePoint state (timelineDeclStart decl)
            endValue <- exprToTimePoint state (timelineDeclEnd decl)
            loopCountValue <- traverse (exprToInteger state) (timelineDeclLoopCount decl)
            forkValue <-
                traverse
                    ( \(name, expr) -> do
                        point <- exprToTimePoint state expr
                        pure (name, point)
                    )
                    (timelineDeclForkFrom decl)
            mergeValue <-
                traverse
                    ( \(name, expr) -> do
                        point <- exprToTimePoint state expr
                        pure (name, point)
                    )
                    (timelineDeclMergeInto decl)
            let world' =
                    (evalWorld state)
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
                                (worldTimelines (evalWorld state))
                        }
            pure state{evalWorld = world'}
        StmtEntity decl -> do
            rejectDuplicate "entity" (entityDeclName decl) (worldEntities (evalWorld state))
            fieldValues <- traverse (evalExpr state) (entityDeclFields decl)
            appearances <-
                traverse
                    ( \appearance ->
                        Appearance
                            (appearanceDeclTimeline appearance)
                            <$> (TimeRange
                                    <$> exprToTimePoint state (appearanceDeclStart appearance)
                                    <*> exprToTimePoint state (appearanceDeclEnd appearance)
                                )
                    )
                    (entityDeclAppearances decl)
            let world' =
                    (evalWorld state)
                        { worldEntities =
                            Map.insert
                                (entityDeclName decl)
                                Entity
                                    { entityName = entityDeclName decl
                                    , entityType = maybe "entity" id (entityDeclType decl)
                                    , entityFields = fieldValues
                                    , entityAppearances = appearances
                                    }
                                (worldEntities (evalWorld state))
                        }
            pure state{evalWorld = world'}
        StmtRelationship decl -> do
            let temporalScopeValue =
                    case relationshipDeclTemporalScope decl of
                        Nothing -> Right Nothing
                        Just (startExpr, endExpr) ->
                            Just
                                <$> (TimeRange
                                        <$> exprToTimePoint state startExpr
                                        <*> exprToTimePoint state endExpr
                                    )
            scope <- temporalScopeValue
            let world' =
                    (evalWorld state)
                        { worldRelationships =
                            worldRelationships (evalWorld state)
                                ++ [ Relationship
                                        { relSource = relationshipDeclSource decl
                                        , relLabel = relationshipDeclLabel decl
                                        , relTarget = relationshipDeclTarget decl
                                        , relDirected = relationshipDeclDirected decl
                                        , relTemporalScope = scope
                                        }
                                   ]
                        }
            pure state{evalWorld = world'}
        StmtImport _ ->
            pure state
        StmtLet decl -> do
            value <- evalExpr state (letValue decl)
            pure state{evalEnv = Map.insert (letName decl) value (evalEnv state)}
        StmtFor decl ->
            evalForLoop state decl
        StmtFunction decl -> do
            let world' =
                    (evalWorld state)
                        { worldFunctions =
                            Map.insert
                                (fnName decl)
                                FunctionSig
                                    { functionName = fnName decl
                                    , functionParams = fnParams decl
                                    }
                                (worldFunctions (evalWorld state))
                        }
            pure state{evalWorld = world'}
        StmtIf decl -> do
            conditionValue <- evalExpr state (ifCondition decl)
            case conditionValue of
                VBool True -> foldM evalStmt state (ifThenBlock decl)
                VBool False -> evalElseBranches state (ifElseIfBlocks decl) (ifElseBlock decl)
                _ ->
                    Left $
                        Diagnostic
                            { diagnosticLevel = DiagnosticError
                            , diagnosticSource = "evaluator"
                            , diagnosticMessage = "if condition must evaluate to a boolean"
                            }

evalExpr :: EvalState -> Expr -> Either Diagnostic Value
evalExpr _ (ExprValue value) = Right value
evalExpr state (ExprIdent name) =
    case Map.lookup name (evalEnv state) of
        Just value -> Right value
        Nothing ->
            Right $
                VString name
evalExpr state (ExprBinary op lhs rhs) = do
    leftValue <- evalExpr state lhs
    rightValue <- evalExpr state rhs
    evalBinary op leftValue rightValue

evalBinary :: BinaryOp -> Value -> Value -> Either Diagnostic Value
evalBinary OpAdd (VInt leftValue) (VInt rightValue) = Right (VInt (leftValue + rightValue))
evalBinary OpSub (VInt leftValue) (VInt rightValue) = Right (VInt (leftValue - rightValue))
evalBinary OpGt (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue > rightValue))
evalBinary OpGt (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue > rightValue))
evalBinary OpLt (VInt leftValue) (VInt rightValue) = Right (VBool (leftValue < rightValue))
evalBinary OpLt (VDate leftValue) (VDate rightValue) = Right (VBool (leftValue < rightValue))
evalBinary OpEq leftValue rightValue = Right (VBool (leftValue == rightValue))
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

exprToTimePoint :: EvalState -> Expr -> Either Diagnostic TimePoint
exprToTimePoint state expr = do
    value <- evalExpr state expr
    case timePointFromValue value of
        Left message ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = message
                    }
        Right point -> Right point

exprToInteger :: EvalState -> Expr -> Either Diagnostic Integer
exprToInteger state expr = do
    value <- evalExpr state expr
    case value of
        VInt intValue -> Right intValue
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
    conditionValue <- evalExpr state conditionExpr
    case conditionValue of
        VBool True -> foldM evalStmt state branchBody
        VBool False -> evalElseBranches state rest elseBlock
        _ ->
            Left $
                Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "evaluator"
                    , diagnosticMessage = "else-if condition must evaluate to a boolean"
                    }

evalForLoop :: EvalState -> ForDecl -> Either Diagnostic EvalState
evalForLoop state decl = do
    values <- evalForIterable state (forIterable decl)
    let previousBinding = Map.lookup (forVar decl) (evalEnv state)
    iteratedState <-
        foldM
            ( \currentState value -> do
                let scopedState =
                        currentState
                            { evalEnv =
                                Map.insert (forVar decl) value (evalEnv currentState)
                            }
                foldM evalStmt scopedState (forBody decl)
            )
            state
            values
    pure iteratedState{evalEnv = restoreBinding previousBinding (forVar decl) (evalEnv iteratedState)}

evalForIterable :: EvalState -> ForIterable -> Either Diagnostic [Value]
evalForIterable state iterable =
    case iterable of
        ForRange startExpr endExpr -> do
            startValue <- exprToInteger state startExpr
            endValue <- exprToInteger state endExpr
            pure $
                map VInt $
                    if startValue <= endValue
                        then [startValue .. endValue]
                        else reverse [endValue .. startValue]
        ForList exprs ->
            traverse (evalExpr state) exprs
        ForExpr expr ->
            pure . pure =<< evalExpr state expr

restoreBinding :: Maybe Value -> Text -> Map Text Value -> Map Text Value
restoreBinding Nothing name env = Map.delete name env
restoreBinding (Just value) name env = Map.insert name value env
