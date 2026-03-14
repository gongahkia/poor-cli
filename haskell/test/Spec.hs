{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import qualified Data.Map.Strict as Map
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Data.Time (fromGregorian)
import Seuss.Config.Loader
import Seuss.Core.Diff
import Seuss.Core.Eval
import Seuss.Core.Validation
import Seuss.Lang.AST
import Seuss.Import.CSV
import Seuss.Lang.Parser
import Seuss.Model.Types
import System.Directory (removeFile)
import Test.Hspec

main :: IO ()
main = hspec spec

spec :: Spec
spec = do
    describe "parser and evaluator" $
        it "loads the LOTR example into a world" $ do
            source <- TIO.readFile "../examples/lotr.seuss"
            case parseProgram "../examples/lotr.seuss" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            Map.size (worldTimelines worldValue) `shouldBe` 1
                            Map.size (worldEntities worldValue) `shouldBe` 4
                            length (worldRelationships worldValue) `shouldBe` 3

    describe "validation" $
        it "accepts the LOTR example without hard errors" $ do
            source <- TIO.readFile "../examples/lotr.seuss"
            case parseProgram "../examples/lotr.seuss" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue ->
                            any ((== DiagnosticError) . diagnosticLevel) (validateWorld worldValue)
                                `shouldBe` False

    describe "csv import" $
        it "creates seuss entity declarations from a CSV schema" $ do
            let csvInput =
                    "name,type,timeline,start,end,age\nfrodo,character,main,2968-09-22,3019-09-29,50\n"
            case importCsvToSeuss csvInput of
                Left diags ->
                    expectationFailure ("csv import failed: " <> show diags)
                Right output ->
                    output `shouldSatisfy` T.isInfixOf "entity frodo"

    describe "config loading" $
        it "reads export defaults and theme settings from a TOML-like file" $ do
            let configPath = "/tmp/seuss-hs-config.toml"
                configSource =
                    T.unlines
                        [ "[export]"
                        , "default_width = 2048"
                        , "default_height = 1152"
                        , "default_format = \"pdf\""
                        , ""
                        , "[theme]"
                        , "name = \"light\""
                        , "background = \"#ffffff\""
                        ]
            TIO.writeFile configPath configSource
            configValue <- loadConfig (Just configPath)
            resolvedTheme <- resolveSvgTheme Nothing configValue
            removeFile configPath
            configDefaultWidth configValue `shouldBe` Just 2048
            configDefaultHeight configValue `shouldBe` Just 1152
            configDefaultFormat configValue `shouldBe` Just "pdf"
            configThemeName configValue `shouldBe` Just "light"
            themeBackground resolvedTheme `shouldBe` "#ffffff"

    describe "import parsing" $
        it "accepts import statements in the Haskell frontend" $ do
            case parseProgram "<inline>" "import \"shared.seuss\";\n" of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program statements) ->
                    statements `shouldBe` [StmtImport "shared.seuss"]

    describe "conditional parsing and evaluation" $ do
        it "parses else-if and else branches into the AST" $ do
            let source =
                    T.unlines
                        [ "if false {"
                        , "  let branch = 0;"
                        , "} else if true {"
                        , "  let branch = 1;"
                        , "} else {"
                        , "  let branch = 2;"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtIf decl]) -> do
                    length (ifElseIfBlocks decl) `shouldBe` 1
                    ifElseBlock decl `shouldSatisfy` (/= Nothing)
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "evaluates the first matching branch in a conditional chain" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2001-01-01,"
                        , "}"
                        , ""
                        , "if false {"
                        , "  entity alpha : event {"
                        , "    appears_on: main @ 2000-01-01..2000-02-01,"
                        , "  }"
                        , "} else if true {"
                        , "  entity beta : event {"
                        , "    appears_on: main @ 2000-03-01..2000-04-01,"
                        , "  }"
                        , "} else {"
                        , "  entity gamma : event {"
                        , "    appears_on: main @ 2000-05-01..2000-06-01,"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            Map.member "alpha" (worldEntities worldValue) `shouldBe` False
                            Map.member "beta" (worldEntities worldValue) `shouldBe` True
                            Map.member "gamma" (worldEntities worldValue) `shouldBe` False

    describe "match parsing and evaluation" $ do
        it "parses literal, binding, and wildcard match arms into the AST" $ do
            let source =
                    T.unlines
                        [ "match status {"
                        , "  \"active\" => { let running = true; },"
                        , "  state => { let seen = state; },"
                        , "  _ => { let running = false; },"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtMatch decl]) ->
                    matchArms decl
                        `shouldBe`
                            [ MatchArm
                                { matchArmPattern = MatchPatternValue (VString "active")
                                , matchArmBody = [StmtLet (LetDecl "running" (ExprValue (VBool True)))]
                                }
                            , MatchArm
                                { matchArmPattern = MatchPatternBind "state"
                                , matchArmBody = [StmtLet (LetDecl "seen" (ExprIdent "state"))]
                                }
                            , MatchArm
                                { matchArmPattern = MatchPatternWildcard
                                , matchArmBody = [StmtLet (LetDecl "running" (ExprValue (VBool False)))]
                                }
                            ]
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "executes the first matching arm and exposes identifier bindings inside that arm" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "let status = \"paused\";"
                        , "match status {"
                        , "  \"active\" => {"
                        , "    entity wrong_branch : event {"
                        , "      appears_on: main @ 2000-01-01..2000-01-02,"
                        , "    }"
                        , "  },"
                        , "  state => {"
                        , "    if state == \"paused\" {"
                        , "      entity bound_branch : event {"
                        , "        appears_on: main @ 2000-02-01..2000-02-02,"
                        , "      }"
                        , "    }"
                        , "  },"
                        , "  _ => {"
                        , "    entity wildcard_branch : event {"
                        , "      appears_on: main @ 2000-03-01..2000-03-02,"
                        , "    }"
                        , "  },"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            Map.member "wrong_branch" (worldEntities worldValue) `shouldBe` False
                            Map.member "bound_branch" (worldEntities worldValue) `shouldBe` True
                            Map.member "wildcard_branch" (worldEntities worldValue) `shouldBe` False

    describe "list and range expression parsing and evaluation" $ do
        it "parses list and range expressions without collapsing appearance ranges" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "entity sample : event {"
                        , "  values: [1, 2, 3],"
                        , "  appears_on: main @ 2000-01-01..2000-02-01,"
                        , "}"
                        , ""
                        , "let days = 1..3;"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtTimeline _, StmtEntity decl, StmtLet letDecl]) -> do
                    Map.lookup "values" (entityDeclFields decl)
                        `shouldBe`
                            Just
                                ( ExprList
                                    [ ExprValue (VInt 1)
                                    , ExprValue (VInt 2)
                                    , ExprValue (VInt 3)
                                    ]
                                )
                    entityDeclAppearances decl
                        `shouldBe`
                            [ AppearanceDecl
                                { appearanceDeclTimeline = "main"
                                , appearanceDeclStart = ExprValue (VDate (fromGregorian 2000 1 1))
                                , appearanceDeclEnd = ExprValue (VDate (fromGregorian 2000 2 1))
                                }
                            ]
                    letValue letDecl `shouldBe` ExprRange (ExprValue (VInt 1)) (ExprValue (VInt 3))
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "evaluates bound list and range expressions as loop iterables" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "let days = 1..3;"
                        , "let labels = [\"one\", \"two\"];"
                        , ""
                        , "for day in days {"
                        , "  if day == 2 {"
                        , "    entity range_hit : event {"
                        , "      appears_on: main @ 2000-04-01..2000-04-02,"
                        , "    }"
                        , "  }"
                        , "}"
                        , ""
                        , "for label in labels {"
                        , "  if label == \"two\" {"
                        , "    entity list_hit : event {"
                        , "      appears_on: main @ 2000-05-01..2000-05-02,"
                        , "    }"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            Map.member "range_hit" (worldEntities worldValue) `shouldBe` True
                            Map.member "list_hit" (worldEntities worldValue) `shouldBe` True

    describe "assignment parsing and evaluation" $ do
        it "parses mutable lets and reassignment statements" $ do
            let source =
                    T.unlines
                        [ "let mut counter = 0;"
                        , "counter = counter + 1;"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtLet decl, StmtAssign name expr]) -> do
                    decl `shouldBe` LetDecl "counter" (ExprValue (VInt 0))
                    name `shouldBe` "counter"
                    expr
                        `shouldBe`
                            ExprBinary
                                OpAdd
                                (ExprIdent "counter")
                                (ExprValue (VInt 1))
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "reassigns loop state inside while-blocks so the condition can change" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "let mut counter = 0;"
                        , "while counter < 3 {"
                        , "  counter = counter + 1;"
                        , "  if counter == 2 {"
                        , "    entity assigned_while_hit : event {"
                        , "      appears_on: main @ 2000-09-01..2000-09-02,"
                        , "    }"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue ->
                            Map.member "assigned_while_hit" (worldEntities worldValue) `shouldBe` True

    describe "boolean and comparison operator evaluation" $
        it "evaluates precedence-sensitive boolean logic with extended comparison operators" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "if true || false && false {"
                        , "  entity precedence_hit : event {"
                        , "    appears_on: main @ 2000-10-01..2000-10-02,"
                        , "  }"
                        , "}"
                        , ""
                        , "if 2 <= 2 && 3 >= 3 && 4 != 5 {"
                        , "  entity comparison_hit : event {"
                        , "    appears_on: main @ 2000-11-01..2000-11-02,"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            Map.member "precedence_hit" (worldEntities worldValue) `shouldBe` True
                            Map.member "comparison_hit" (worldEntities worldValue) `shouldBe` True

    describe "for-loop parsing and evaluation" $ do
        it "parses list and range iterables for for-loops" $ do
            let source =
                    T.unlines
                        [ "for item in [1, 2, 3] {"
                        , "  let seen = item;"
                        , "}"
                        , ""
                        , "for day in 1..3 {"
                        , "  let seen = day;"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtFor listLoop, StmtFor rangeLoop]) -> do
                    forIterable listLoop `shouldBe` ForList [ExprValue (VInt 1), ExprValue (VInt 2), ExprValue (VInt 3)]
                    forIterable rangeLoop `shouldBe` ForRange (ExprValue (VInt 1)) (ExprValue (VInt 3))
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "iterates integer ranges and exposes the loop variable to the body" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "for i in 1..3 {"
                        , "  if i == 2 {"
                        , "    entity middle : event {"
                        , "      appears_on: main @ 2000-02-01..2000-02-02,"
                        , "    }"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue ->
                            Map.member "middle" (worldEntities worldValue) `shouldBe` True

    describe "repeat-loop parsing and evaluation" $ do
        it "parses repeat-loops into the AST" $ do
            case parseProgram "<inline>" "repeat 3 { let seen = 1; }\n" of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtRepeat decl]) ->
                    repeatCount decl `shouldBe` ExprValue (VInt 3)
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "replays the repeat body the requested number of times" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "let target = 2;"
                        , "for i in 1..3 {"
                        , "  repeat 1 {"
                        , "    if i == target {"
                        , "      entity repeated_hit : event {"
                        , "        appears_on: main @ 2000-07-01..2000-07-02,"
                        , "      }"
                        , "    }"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue ->
                            Map.member "repeated_hit" (worldEntities worldValue) `shouldBe` True

    describe "while-loop parsing and evaluation" $ do
        it "parses while-loops into the AST" $ do
            case parseProgram "<inline>" "while true { let seen = 1; }\n" of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right (Program [StmtWhile decl]) ->
                    whileCondition decl `shouldBe` ExprValue (VBool True)
                Right other ->
                    expectationFailure ("unexpected parse result: " <> show other)

        it "re-evaluates the condition until the while-loop becomes false" $ do
            let source =
                    T.unlines
                        [ "timeline main {"
                        , "  kind: linear,"
                        , "  start: 2000-01-01,"
                        , "  end: 2000-12-31,"
                        , "}"
                        , ""
                        , "let counter = 0;"
                        , "while counter < 3 {"
                        , "  let counter = counter + 1;"
                        , "  if counter == 2 {"
                        , "    entity while_hit : event {"
                        , "      appears_on: main @ 2000-08-01..2000-08-02,"
                        , "    }"
                        , "  }"
                        , "}"
                        ]
            case parseProgram "<inline>" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue ->
                            Map.member "while_hit" (worldEntities worldValue) `shouldBe` True

    describe "diffing" $
        it "reports entity deltas between worlds" $ do
            source <- TIO.readFile "../examples/lotr.seuss"
            case parseProgram "../examples/lotr.seuss" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            let smallerWorld = worldValue{worldEntities = Map.delete "ring" (worldEntities worldValue)}
                                diffText = diffWorlds smallerWorld worldValue
                            diffText `shouldSatisfy` T.isInfixOf "ring"

        it "reports changed entity details when shared names diverge" $ do
            source <- TIO.readFile "../examples/lotr.seuss"
            case parseProgram "../examples/lotr.seuss" source of
                Left diags ->
                    expectationFailure ("parse failed: " <> show diags)
                Right program ->
                    case evalProgram program of
                        Left diag ->
                            expectationFailure ("eval failed: " <> show diag)
                        Right worldValue -> do
                            let updatedRing =
                                    fmap (\entity -> entity{entityType = "object"}) (Map.lookup "ring" (worldEntities worldValue))
                                changedWorld =
                                    case updatedRing of
                                        Nothing -> worldValue
                                        Just ringEntity ->
                                            worldValue{worldEntities = Map.insert "ring" ringEntity (worldEntities worldValue)}
                                diffText = diffWorlds worldValue changedWorld
                            diffText `shouldSatisfy` T.isInfixOf "~ changed ring"
