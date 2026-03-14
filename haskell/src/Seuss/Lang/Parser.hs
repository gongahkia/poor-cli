{-# LANGUAGE OverloadedStrings #-}

module Seuss.Lang.Parser
    ( parseProgram
    , parseStatement
    ) where

import Control.Applicative (empty, many, optional, (<|>))
import Data.Char (isAlphaNum)
import Data.Functor (($>))
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import Data.Time (Day, defaultTimeLocale, parseTimeM)
import Data.Void (Void)
import Control.Monad.Combinators.Expr (Operator(..), makeExprParser)
import Seuss.Lang.AST
import Seuss.Model.Types
import Text.Megaparsec
import Text.Megaparsec.Char
import qualified Text.Megaparsec.Char.Lexer as L

type Parser = Parsec Void Text

parseProgram :: FilePath -> Text -> Either [Diagnostic] Program
parseProgram file input =
    case runParser (between sc eof (Program <$> many statementParser)) file input of
        Left bundle ->
            Left
                [ Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "parser"
                    , diagnosticMessage = T.pack (errorBundlePretty bundle)
                    }
                ]
        Right program -> Right program

parseStatement :: FilePath -> Text -> Either [Diagnostic] Stmt
parseStatement file input =
    case runParser (between sc eof statementParser) file input of
        Left bundle ->
            Left
                [ Diagnostic
                    { diagnosticLevel = DiagnosticError
                    , diagnosticSource = "parser"
                    , diagnosticMessage = T.pack (errorBundlePretty bundle)
                    }
                ]
        Right statement -> Right statement

statementParser :: Parser Stmt
statementParser =
    choice
        [ StmtType <$> typeDeclParser
        , StmtTimeline <$> timelineDeclParser
        , StmtEntity <$> entityDeclParser
        , StmtRelationship <$> relationshipDeclParser
        , StmtImport <$> importStmtParser
        , StmtLet <$> letDeclParser
        , StmtFor <$> forDeclParser
        , StmtFunction <$> fnDeclParser
        , StmtIf <$> ifDeclParser
        ]

sc :: Parser ()
sc =
    L.space
        space1
        (L.skipLineComment "//")
        (L.skipBlockComment "/*" "*/")

lexeme :: Parser a -> Parser a
lexeme = L.lexeme sc

symbol :: Text -> Parser Text
symbol = L.symbol sc

identifier :: Parser Text
identifier = lexeme $ do
    first <- letterChar <|> char '_'
    rest <- many (satisfy (\c -> isAlphaNum c || c == '_'))
    pure (T.pack (first : rest))

stringLiteral :: Parser Text
stringLiteral = T.pack <$> lexeme (char '"' *> manyTill L.charLiteral (char '"'))

dateLiteral :: Parser Day
dateLiteral = lexeme $ try $ do
    year <- count 4 digitChar
    _ <- char '-'
    month <- count 2 digitChar
    _ <- char '-'
    day <- count 2 digitChar
    let textValue = year <> "-" <> month <> "-" <> day
    maybe empty pure $
        parseTimeM True defaultTimeLocale "%F" textValue

integerLiteral :: Parser Integer
integerLiteral = lexeme (L.signed sc L.decimal)

boolLiteral :: Parser Bool
boolLiteral =
    (symbol "true" $> True)
        <|> (symbol "false" $> False)

exprParser :: Parser Expr
exprParser = makeExprParser term operatorTable

term :: Parser Expr
term =
    choice
        [ ExprValue . VDate <$> try dateLiteral
        , ExprValue . VBool <$> boolLiteral
        , ExprValue . VInt <$> try integerLiteral
        , ExprValue . VString <$> stringLiteral
        , ExprIdent <$> identifier
        , between (symbol "(") (symbol ")") exprParser
        ]

operatorTable :: [[Operator Parser Expr]]
operatorTable =
    [ [binary "+" (ExprBinary OpAdd), binary "-" (ExprBinary OpSub)]
    , [binary ">" (ExprBinary OpGt), binary "<" (ExprBinary OpLt), binary "==" (ExprBinary OpEq)]
    ]

binary :: Text -> (Expr -> Expr -> Expr) -> Operator Parser Expr
binary name f = InfixL (f <$ symbol name)

typeDeclParser :: Parser TypeDecl
typeDeclParser = do
    _ <- symbol "type"
    name <- identifier
    parent <- optional (symbol ":" *> identifier)
    fields <- braces (many typeFieldParser)
    pure
        TypeDecl
            { typeDeclName = name
            , typeDeclParent = parent
            , typeDeclFields = fields
            }

typeFieldParser :: Parser TypeField
typeFieldParser = do
    fieldName <- identifier
    _ <- symbol ":"
    fieldType <- identifier
    _ <- optional (symbol ",")
    pure
        TypeField
            { typeFieldName = fieldName
            , typeFieldType = fieldType
            , typeFieldOptional = False
            }

timelineDeclParser :: Parser TimelineDecl
timelineDeclParser = do
    _ <- symbol "timeline"
    name <- identifier
    fields <- braces (many timelineFieldParser)
    let kindValue = maybe TimelineLinear id (extractField "kind" fields >>= asTimelineKind)
        startValue = maybe (ExprValue (VInt 0)) id (extractField "start" fields)
        endValue = maybe (ExprValue (VInt 100)) id (extractField "end" fields)
        parentValue = extractField "parent" fields >>= asIdentifier
        forkValue = extractField "fork_from" fields >>= asTimelineRef
        mergeValue = extractField "merge_into" fields >>= asTimelineRef
        loopValue = extractField "loop_count" fields
    pure
        TimelineDecl
            { timelineDeclName = name
            , timelineDeclKind = kindValue
            , timelineDeclStart = startValue
            , timelineDeclEnd = endValue
            , timelineDeclParent = parentValue
            , timelineDeclForkFrom = forkValue
            , timelineDeclMergeInto = mergeValue
            , timelineDeclLoopCount = loopValue
            }

entityDeclParser :: Parser EntityDecl
entityDeclParser = do
    _ <- symbol "entity"
    name <- identifier
    entityType <- optional (symbol ":" *> identifier)
    fields <- braces (many entityFieldParser)
    let customFields =
            Map.fromList
                [ (fieldName, expr)
                | EntityField fieldName expr <- fields
                ]
        appearances =
            [ appearance
            | AppearanceField appearance <- fields
            ]
    pure
        EntityDecl
            { entityDeclName = name
            , entityDeclType = entityType
            , entityDeclFields = customFields
            , entityDeclAppearances = appearances
            }

relationshipDeclParser :: Parser RelationshipDecl
relationshipDeclParser = do
    _ <- symbol "rel"
    source <- identifier
    (labelValue, directedValue) <-
        try labeledArrow <|> unlabeledArrow
    target <- identifier
    temporalScope <- optional $ do
        _ <- symbol "@"
        startValue <- exprParser
        _ <- symbol ".."
        endValue <- exprParser
        pure (startValue, endValue)
    _ <- symbol ";"
    pure
        RelationshipDecl
            { relationshipDeclSource = source
            , relationshipDeclLabel = labelValue
            , relationshipDeclTarget = target
            , relationshipDeclDirected = directedValue
            , relationshipDeclTemporalScope = temporalScope
            }

importStmtParser :: Parser Text
importStmtParser = do
    _ <- symbol "import"
    pathValue <- stringLiteral
    _ <- symbol ";"
    pure pathValue

letDeclParser :: Parser LetDecl
letDeclParser = do
    _ <- symbol "let"
    name <- identifier
    _ <- symbol "="
    value <- exprParser
    _ <- optional (symbol ";")
    pure (LetDecl name value)

forDeclParser :: Parser ForDecl
forDeclParser = do
    _ <- symbol "for"
    loopVar <- identifier
    _ <- symbol "in"
    iterable <- forIterableParser
    body <- braces (many statementParser)
    pure
        ForDecl
            { forVar = loopVar
            , forIterable = iterable
            , forBody = body
            }

forIterableParser :: Parser ForIterable
forIterableParser =
    try forRangeParser <|> try forListParser <|> (ForExpr <$> exprParser)

forRangeParser :: Parser ForIterable
forRangeParser = do
    startExpr <- term
    _ <- symbol ".."
    endExpr <- exprParser
    pure (ForRange startExpr endExpr)

forListParser :: Parser ForIterable
forListParser =
    ForList <$> between (symbol "[") (symbol "]") (exprParser `sepBy` symbol ",")

fnDeclParser :: Parser FnDecl
fnDeclParser = do
    _ <- symbol "fn"
    name <- identifier
    params <- parens (paramParser `sepBy` symbol ",")
    body <- braces (many statementParser)
    pure
        FnDecl
            { fnName = name
            , fnParams = params
            , fnBody = body
            }

paramParser :: Parser (Text, Text)
paramParser = do
    name <- identifier
    _ <- symbol ":"
    typeName <- identifier
    pure (name, typeName)

ifDeclParser :: Parser IfDecl
ifDeclParser = do
    _ <- symbol "if"
    condition <- exprParser
    body <- braces (many statementParser)
    elseIfBlocks <- many elseIfParser
    elseBlock <- optional elseBlockParser
    pure
        IfDecl
            { ifCondition = condition
            , ifThenBlock = body
            , ifElseIfBlocks = elseIfBlocks
            , ifElseBlock = elseBlock
            }

elseIfParser :: Parser (Expr, [Stmt])
elseIfParser = do
    _ <- symbol "else"
    _ <- symbol "if"
    condition <- exprParser
    body <- braces (many statementParser)
    pure (condition, body)

elseBlockParser :: Parser [Stmt]
elseBlockParser = do
    _ <- symbol "else"
    braces (many statementParser)

data EntityFieldEntry
    = EntityField Text Expr
    | AppearanceField AppearanceDecl

entityFieldParser :: Parser EntityFieldEntry
entityFieldParser =
    try appearanceFieldParser <|> genericFieldParser

genericFieldParser :: Parser EntityFieldEntry
genericFieldParser = do
    fieldName <- identifier
    _ <- symbol ":"
    value <- exprParser
    _ <- optional (symbol ",")
    pure (EntityField fieldName value)

appearanceFieldParser :: Parser EntityFieldEntry
appearanceFieldParser = do
    _ <- symbol "appears_on"
    _ <- symbol ":"
    timelineName <- identifier
    _ <- symbol "@"
    startValue <- exprParser
    _ <- symbol ".."
    endValue <- exprParser
    _ <- optional (symbol ",")
    pure $
        AppearanceField
            AppearanceDecl
                { appearanceDeclTimeline = timelineName
                , appearanceDeclStart = startValue
                , appearanceDeclEnd = endValue
                }

timelineFieldParser :: Parser (Text, Expr)
timelineFieldParser = do
    fieldName <- identifier
    _ <- symbol ":"
    value <- try timelineRefExprParser <|> exprParser
    _ <- optional (symbol ",")
    pure (fieldName, value)

timelineRefExprParser :: Parser Expr
timelineRefExprParser = do
    timelineName <- identifier
    _ <- symbol "@"
    point <- exprParser
    pure (ExprBinary OpEq (ExprIdent timelineName) point)

labeledArrow :: Parser (Maybe Text, Bool)
labeledArrow = do
    _ <- symbol "-["
    labelValue <- stringLiteral
    _ <- symbol "]->"
    pure (Just labelValue, True)

unlabeledArrow :: Parser (Maybe Text, Bool)
unlabeledArrow = do
    _ <- symbol "-->"
    pure (Nothing, True)

braces :: Parser a -> Parser a
braces = between (symbol "{") (symbol "}")

parens :: Parser a -> Parser a
parens = between (symbol "(") (symbol ")")

extractField :: Text -> [(Text, Expr)] -> Maybe Expr
extractField fieldName = lookup fieldName

asIdentifier :: Expr -> Maybe Text
asIdentifier (ExprIdent name) = Just name
asIdentifier _ = Nothing

asTimelineKind :: Expr -> Maybe TimelineKind
asTimelineKind (ExprIdent "linear") = Just TimelineLinear
asTimelineKind (ExprIdent "branch") = Just TimelineBranch
asTimelineKind (ExprIdent "parallel") = Just TimelineParallel
asTimelineKind (ExprIdent "loop") = Just TimelineLoop
asTimelineKind _ = Nothing

asTimelineRef :: Expr -> Maybe (Text, Expr)
asTimelineRef (ExprBinary OpEq (ExprIdent name) point) = Just (name, point)
asTimelineRef _ = Nothing
