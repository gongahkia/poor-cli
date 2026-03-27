{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE PatternSynonyms #-}

module Seuss.Lang.AST
    ( AppearanceDecl(..)
    , EntityDecl(..)
    , Expr(..)
    , FnDecl(..)
    , ForDecl(..)
    , ForIterable(..)
    , IfDecl(..)
    , LetDecl(..)
    , MatchArm(..)
    , MatchDecl(..)
    , MatchPattern(..)
    , Program(..)
    , pattern Program
    , RepeatDecl(..)
    , RelationshipDecl(..)
    , Stmt(..)
    , pattern StmtAssign
    , pattern StmtEntity
    , pattern StmtExpr
    , pattern StmtFor
    , pattern StmtFunction
    , pattern StmtIf
    , pattern StmtImport
    , pattern StmtLet
    , pattern StmtMatch
    , pattern StmtRelationship
    , pattern StmtRepeat
    , pattern StmtReturn
    , pattern StmtTimeline
    , pattern StmtType
    , pattern StmtWhile
    , StmtNode(..)
    , TimelineDecl(..)
    , TypeDecl(..)
    , WhileDecl(..)
    ) where

import Data.Map.Strict (Map)
import Data.Text (Text)
import Seuss.Model.Types (BinaryOp(..), SourceSpan, TypeField(..), Value(..), noSourceSpan)

data Expr
    = ExprValue Value
    | ExprIdent Text
    | ExprList [Expr]
    | ExprRange Expr Expr
    | ExprIndex Expr Expr
    | ExprField Expr Text
    | ExprCall Expr [Expr]
    | ExprClosure [(Text, Text)] Expr
    | ExprBinary BinaryOp Expr Expr
    deriving (Eq, Show)

data TypeDecl = TypeDecl
    { typeDeclName :: Text
    , typeDeclParent :: Maybe Text
    , typeDeclFields :: [TypeField]
    , typeDeclMeta :: Map Text Expr
    }
    deriving (Eq, Show)

data TimelineDecl = TimelineDecl
    { timelineDeclName :: Text
    , timelineDeclKind :: Maybe Expr
    , timelineDeclStart :: Expr
    , timelineDeclEnd :: Expr
    , timelineDeclParent :: Maybe Text
    , timelineDeclForkFrom :: Maybe (Text, Expr)
    , timelineDeclMergeInto :: Maybe (Text, Expr)
    , timelineDeclLoopCount :: Maybe Expr
    }
    deriving (Eq, Show)

data AppearanceDecl = AppearanceDecl
    { appearanceDeclTimeline :: Text
    , appearanceDeclStart :: Expr
    , appearanceDeclEnd :: Expr
    }
    deriving (Eq, Show)

data EntityDecl = EntityDecl
    { entityDeclName :: Text
    , entityDeclType :: Maybe Text
    , entityDeclFields :: Map Text Expr
    , entityDeclAppearances :: [AppearanceDecl]
    }
    deriving (Eq, Show)

data RelationshipDecl = RelationshipDecl
    { relationshipDeclSource :: Text
    , relationshipDeclLabel :: Maybe Text
    , relationshipDeclTarget :: Text
    , relationshipDeclDirected :: Bool
    , relationshipDeclTemporalScope :: Maybe (Expr, Expr)
    }
    deriving (Eq, Show)

data LetDecl = LetDecl
    { letName :: Text
    , letMutable :: Bool
    , letTypeAnnotation :: Maybe Text
    , letValue :: Expr
    }
    deriving (Eq, Show)

data ForIterable
    = ForRange Expr Expr
    | ForList [Expr]
    | ForExpr Expr
    deriving (Eq, Show)

data ForDecl = ForDecl
    { forVar :: Text
    , forIterable :: ForIterable
    , forBody :: [Stmt]
    }
    deriving (Eq, Show)

data RepeatDecl = RepeatDecl
    { repeatCount :: Expr
    , repeatBody :: [Stmt]
    }
    deriving (Eq, Show)

data WhileDecl = WhileDecl
    { whileCondition :: Expr
    , whileBody :: [Stmt]
    }
    deriving (Eq, Show)

data FnDecl = FnDecl
    { fnName :: Text
    , fnParams :: [(Text, Text)]
    , fnReturnType :: Maybe Text
    , fnBody :: [Stmt]
    }
    deriving (Eq, Show)

data IfDecl = IfDecl
    { ifCondition :: Expr
    , ifThenBlock :: [Stmt]
    , ifElseIfBlocks :: [(Expr, [Stmt])]
    , ifElseBlock :: Maybe [Stmt]
    }
    deriving (Eq, Show)

data MatchPattern
    = MatchPatternValue Value
    | MatchPatternBind Text
    | MatchPatternWildcard
    deriving (Eq, Show)

data MatchArm = MatchArm
    { matchArmPattern :: MatchPattern
    , matchArmBody :: [Stmt]
    }
    deriving (Eq, Show)

data MatchDecl = MatchDecl
    { matchSubject :: Expr
    , matchArms :: [MatchArm]
    }
    deriving (Eq, Show)

data StmtNode
    = StmtTypeNode TypeDecl
    | StmtTimelineNode TimelineDecl
    | StmtEntityNode EntityDecl
    | StmtRelationshipNode RelationshipDecl
    | StmtImportNode Text
    | StmtLetNode LetDecl
    | StmtForNode ForDecl
    | StmtRepeatNode RepeatDecl
    | StmtWhileNode WhileDecl
    | StmtFunctionNode FnDecl
    | StmtIfNode IfDecl
    | StmtMatchNode MatchDecl
    | StmtReturnNode (Maybe Expr)
    | StmtAssignNode Text Expr
    | StmtExprNode Expr
    deriving (Eq, Show)

data Stmt = StmtData
    { stmtSpan :: SourceSpan
    , stmtNode :: StmtNode
    }
    deriving (Show)

instance Eq Stmt where
    left == right = stmtNode left == stmtNode right

pattern StmtType :: TypeDecl -> Stmt
pattern StmtType decl <- StmtData _ (StmtTypeNode decl)
  where
    StmtType decl = StmtData noSourceSpan (StmtTypeNode decl)

pattern StmtTimeline :: TimelineDecl -> Stmt
pattern StmtTimeline decl <- StmtData _ (StmtTimelineNode decl)
  where
    StmtTimeline decl = StmtData noSourceSpan (StmtTimelineNode decl)

pattern StmtEntity :: EntityDecl -> Stmt
pattern StmtEntity decl <- StmtData _ (StmtEntityNode decl)
  where
    StmtEntity decl = StmtData noSourceSpan (StmtEntityNode decl)

pattern StmtRelationship :: RelationshipDecl -> Stmt
pattern StmtRelationship decl <- StmtData _ (StmtRelationshipNode decl)
  where
    StmtRelationship decl = StmtData noSourceSpan (StmtRelationshipNode decl)

pattern StmtImport :: Text -> Stmt
pattern StmtImport pathValue <- StmtData _ (StmtImportNode pathValue)
  where
    StmtImport pathValue = StmtData noSourceSpan (StmtImportNode pathValue)

pattern StmtLet :: LetDecl -> Stmt
pattern StmtLet decl <- StmtData _ (StmtLetNode decl)
  where
    StmtLet decl = StmtData noSourceSpan (StmtLetNode decl)

pattern StmtFor :: ForDecl -> Stmt
pattern StmtFor decl <- StmtData _ (StmtForNode decl)
  where
    StmtFor decl = StmtData noSourceSpan (StmtForNode decl)

pattern StmtRepeat :: RepeatDecl -> Stmt
pattern StmtRepeat decl <- StmtData _ (StmtRepeatNode decl)
  where
    StmtRepeat decl = StmtData noSourceSpan (StmtRepeatNode decl)

pattern StmtWhile :: WhileDecl -> Stmt
pattern StmtWhile decl <- StmtData _ (StmtWhileNode decl)
  where
    StmtWhile decl = StmtData noSourceSpan (StmtWhileNode decl)

pattern StmtFunction :: FnDecl -> Stmt
pattern StmtFunction decl <- StmtData _ (StmtFunctionNode decl)
  where
    StmtFunction decl = StmtData noSourceSpan (StmtFunctionNode decl)

pattern StmtIf :: IfDecl -> Stmt
pattern StmtIf decl <- StmtData _ (StmtIfNode decl)
  where
    StmtIf decl = StmtData noSourceSpan (StmtIfNode decl)

pattern StmtMatch :: MatchDecl -> Stmt
pattern StmtMatch decl <- StmtData _ (StmtMatchNode decl)
  where
    StmtMatch decl = StmtData noSourceSpan (StmtMatchNode decl)

pattern StmtReturn :: Maybe Expr -> Stmt
pattern StmtReturn maybeExpr <- StmtData _ (StmtReturnNode maybeExpr)
  where
    StmtReturn maybeExpr = StmtData noSourceSpan (StmtReturnNode maybeExpr)

pattern StmtAssign :: Text -> Expr -> Stmt
pattern StmtAssign name expr <- StmtData _ (StmtAssignNode name expr)
  where
    StmtAssign name expr = StmtData noSourceSpan (StmtAssignNode name expr)

pattern StmtExpr :: Expr -> Stmt
pattern StmtExpr expr <- StmtData _ (StmtExprNode expr)
  where
    StmtExpr expr = StmtData noSourceSpan (StmtExprNode expr)

{-# COMPLETE
    StmtType,
    StmtTimeline,
    StmtEntity,
    StmtRelationship,
    StmtImport,
    StmtLet,
    StmtFor,
    StmtRepeat,
    StmtWhile,
    StmtFunction,
    StmtIf,
    StmtMatch,
    StmtReturn,
    StmtAssign,
    StmtExpr
    #-}

data Program = ProgramData
    { programFile :: FilePath
    , programStatements :: [Stmt]
    }
    deriving (Show)

instance Eq Program where
    left == right = programStatements left == programStatements right

pattern Program :: [Stmt] -> Program
pattern Program statements <- ProgramData _ statements
  where
    Program statements = ProgramData "<unknown>" statements

{-# COMPLETE Program #-}
