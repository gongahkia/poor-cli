{-# LANGUAGE OverloadedStrings #-}

module Seuss.Lang.Parser
    ( parseProgram
    , parseStatement
    ) where

import Data.Char (isAlphaNum)
import Data.Functor (($>))
import qualified Data.Map.Strict as Map
import Data.Maybe (isJust)
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
        , StmtRepeat <$> repeatDeclParser
        , StmtWhile <$> whileDeclParser
        , StmtFunction <$> fnDeclParser
        , StmtIf <$> ifDeclParser
        , StmtMatch <$> matchDeclParser
        , StmtReturn <$> returnStmtParser
        , try (uncurry StmtAssign <$> assignStmtParser)
        , StmtExpr <$> exprStmtParser
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
exprParser = rangeExprParser

rangeExprParser :: Parser Expr
rangeExprParser = do
    startExpr <- nonRangeExprParser
    maybeEndExpr <- optional (try (symbol ".." *> rangeExprParser))
    pure $
        case maybeEndExpr of
            Nothing -> startExpr
            Just endExpr -> ExprRange startExpr endExpr

nonRangeExprParser :: Parser Expr
nonRangeExprParser = makeExprParser term operatorTable

term :: Parser Expr
term = do
    baseExpr <- primaryTerm
    suffixes <- many postfixSuffixParser
    pure (foldl applyPostfixSuffix baseExpr suffixes)

primaryTerm :: Parser Expr
primaryTerm =
    choice
        [ try closureExprParser
        , ExprValue <$> literalValueParser
        , ExprList <$> between (symbol "[") (symbol "]") (exprParser `sepBy` symbol ",")
        , ExprIdent <$> identifier
        , between (symbol "(") (symbol ")") exprParser
        ]

closureExprParser :: Parser Expr
closureExprParser = do
    _ <- symbol "|"
    params <- paramParser `sepBy` symbol ","
    _ <- symbol "|"
    bodyExpr <- exprParser
    pure (ExprClosure params bodyExpr)

indexSuffixParser :: Parser Expr
indexSuffixParser =
    between (symbol "[") (symbol "]") exprParser

data PostfixSuffix
    = PostfixIndex Expr
    | PostfixField Text
    | PostfixCall [Expr]

postfixSuffixParser :: Parser PostfixSuffix
postfixSuffixParser =
    choice
        [ PostfixIndex <$> indexSuffixParser
        , PostfixField <$> fieldSuffixParser
        , PostfixCall <$> callSuffixParser
        ]

fieldSuffixParser :: Parser Text
fieldSuffixParser = try $ do
    _ <- symbol "."
    identifier

callSuffixParser :: Parser [Expr]
callSuffixParser =
    between (symbol "(") (symbol ")") (exprParser `sepBy` symbol ",")

applyPostfixSuffix :: Expr -> PostfixSuffix -> Expr
applyPostfixSuffix expr suffix =
    case suffix of
        PostfixIndex indexExpr -> ExprIndex expr indexExpr
        PostfixField fieldName -> ExprField expr fieldName
        PostfixCall args -> ExprCall expr args

literalValueParser :: Parser Value
literalValueParser =
    choice
        [ VDate <$> try dateLiteral
        , VBool <$> boolLiteral
        , VInt <$> try integerLiteral
        , VString <$> stringLiteral
        ]

operatorTable :: [[Operator Parser Expr]]
operatorTable =
    [ [binary "+" (ExprBinary OpAdd), binary "-" (ExprBinary OpSub)]
    , [ binary ">=" (ExprBinary OpGte)
      , binary "<=" (ExprBinary OpLte)
      , binary ">" (ExprBinary OpGt)
      , binary "<" (ExprBinary OpLt)
      , binary "==" (ExprBinary OpEq)
      , binary "!=" (ExprBinary OpNeq)
      ]
    , [binary "&&" (ExprBinary OpAnd)]
    , [binary "||" (ExprBinary OpOr)]
    ]

binary :: Text -> (Expr -> Expr -> Expr) -> Operator Parser Expr
binary name f = InfixL (f <$ symbol name)

typeDeclParser :: Parser TypeDecl
typeDeclParser = do
    _ <- symbol "type"
    name <- identifier
    parent <- optional (symbol ":" *> identifier)
    entries <- braces (many typeDeclEntryParser)
    let fields =
            [ field
            | TypeDeclField field <- entries
            ]
        metaFields =
            Map.fromList
                [ (metaName, metaValue)
                | TypeDeclMeta metaName metaValue <- entries
                ]
    pure
        TypeDecl
            { typeDeclName = name
            , typeDeclParent = parent
            , typeDeclFields = fields
            , typeDeclMeta = metaFields
            }

data TypeDeclEntry
    = TypeDeclField TypeField
    | TypeDeclMeta Text Expr

typeDeclEntryParser :: Parser TypeDeclEntry
typeDeclEntryParser =
    try typeMetaParser <|> typeFieldParser

typeFieldParser :: Parser TypeDeclEntry
typeFieldParser = do
    fieldName <- identifier
    _ <- symbol ":"
    fieldType <- identifier
    optionalFlag <- isJust <$> optional (symbol "?")
    _ <- optional (symbol ",")
    pure $
        TypeDeclField
            TypeField
                { typeFieldName = fieldName
                , typeFieldType = fieldType
                , typeFieldOptional = optionalFlag
                }

typeMetaParser :: Parser TypeDeclEntry
typeMetaParser = do
    _ <- symbol "@"
    metaName <- identifier
    _ <- symbol ":"
    metaValue <- exprParser
    _ <- optional (symbol ",")
    pure (TypeDeclMeta metaName metaValue)

timelineDeclParser :: Parser TimelineDecl
timelineDeclParser = do
    _ <- symbol "timeline"
    name <- identifier
    fields <- braces (many timelineFieldParser)
    let kindValue = extractField "kind" fields
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
        startValue <- nonRangeExprParser
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
    isMutable <- isJust <$> optional (symbol "mut")
    name <- identifier
    typeAnnotation <- optional (symbol ":" *> identifier)
    _ <- symbol "="
    value <- exprParser
    _ <- optional (symbol ";")
    pure
        LetDecl
            { letName = name
            , letMutable = isMutable
            , letTypeAnnotation = typeAnnotation
            , letValue = value
            }

assignStmtParser :: Parser (Text, Expr)
assignStmtParser = do
    name <- identifier
    _ <- symbol "="
    value <- exprParser
    _ <- optional (symbol ";")
    pure (name, value)

exprStmtParser :: Parser Expr
exprStmtParser = do
    value <- exprParser
    _ <- optional (symbol ";")
    pure value

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
    startExpr <- nonRangeExprParser
    _ <- symbol ".."
    endExpr <- exprParser
    pure (ForRange startExpr endExpr)

forListParser :: Parser ForIterable
forListParser =
    ForList <$> between (symbol "[") (symbol "]") (exprParser `sepBy` symbol ",")

repeatDeclParser :: Parser RepeatDecl
repeatDeclParser = do
    _ <- symbol "repeat"
    countExpr <- exprParser
    body <- braces (many statementParser)
    pure
        RepeatDecl
            { repeatCount = countExpr
            , repeatBody = body
            }

whileDeclParser :: Parser WhileDecl
whileDeclParser = do
    _ <- symbol "while"
    conditionExpr <- exprParser
    body <- braces (many statementParser)
    pure
        WhileDecl
            { whileCondition = conditionExpr
            , whileBody = body
            }

fnDeclParser :: Parser FnDecl
fnDeclParser = do
    _ <- symbol "fn"
    name <- identifier
    params <- parens (paramParser `sepBy` symbol ",")
    returnType <- optional (symbol "->" *> identifier)
    body <- braces (many statementParser)
    pure
        FnDecl
            { fnName = name
            , fnParams = params
            , fnReturnType = returnType
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
    elseIfBlocks <- many (try elseIfParser)
    elseBlock <- optional elseBlockParser
    pure
        IfDecl
            { ifCondition = condition
            , ifThenBlock = body
            , ifElseIfBlocks = elseIfBlocks
            , ifElseBlock = elseBlock
            }

matchDeclParser :: Parser MatchDecl
matchDeclParser = do
    _ <- symbol "match"
    subjectExpr <- exprParser
    arms <- braces (many matchArmParser)
    pure
        MatchDecl
            { matchSubject = subjectExpr
            , matchArms = arms
            }

returnStmtParser :: Parser (Maybe Expr)
returnStmtParser = do
    _ <- symbol "return"
    valueExpr <- optional exprParser
    _ <- optional (symbol ";")
    pure valueExpr

matchArmParser :: Parser MatchArm
matchArmParser = do
    patternValue <- matchPatternParser
    _ <- symbol "=>"
    body <- braces (many statementParser)
    _ <- optional (symbol ",")
    pure
        MatchArm
            { matchArmPattern = patternValue
            , matchArmBody = body
            }

matchPatternParser :: Parser MatchPattern
matchPatternParser =
    choice
        [ symbol "_" $> MatchPatternWildcard
        , MatchPatternValue <$> try literalValueParser
        , MatchPatternBind <$> identifier
        ]

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
    startValue <- nonRangeExprParser
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

asTimelineRef :: Expr -> Maybe (Text, Expr)
asTimelineRef (ExprBinary OpEq (ExprIdent name) point) = Just (name, point)
asTimelineRef _ = Nothing
