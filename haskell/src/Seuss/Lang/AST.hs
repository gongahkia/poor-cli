{-# LANGUAGE OverloadedStrings #-}

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
    , RepeatDecl(..)
    , RelationshipDecl(..)
    , Stmt(..)
    , TimelineDecl(..)
    , TypeDecl(..)
    , WhileDecl(..)
    ) where

import Data.Map.Strict (Map)
import Data.Text (Text)
import Seuss.Model.Types (BinaryOp(..), TimelineKind(..), TypeField(..), Value(..))

data Expr
    = ExprValue Value
    | ExprIdent Text
    | ExprList [Expr]
    | ExprRange Expr Expr
    | ExprBinary BinaryOp Expr Expr
    deriving (Eq, Show)

data TypeDecl = TypeDecl
    { typeDeclName :: Text
    , typeDeclParent :: Maybe Text
    , typeDeclFields :: [TypeField]
    }
    deriving (Eq, Show)

data TimelineDecl = TimelineDecl
    { timelineDeclName :: Text
    , timelineDeclKind :: TimelineKind
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

data Stmt
    = StmtType TypeDecl
    | StmtTimeline TimelineDecl
    | StmtEntity EntityDecl
    | StmtRelationship RelationshipDecl
    | StmtImport Text
    | StmtLet LetDecl
    | StmtFor ForDecl
    | StmtRepeat RepeatDecl
    | StmtWhile WhileDecl
    | StmtFunction FnDecl
    | StmtIf IfDecl
    | StmtMatch MatchDecl
    | StmtAssign Text Expr
    deriving (Eq, Show)

newtype Program = Program [Stmt]
    deriving (Eq, Show)
