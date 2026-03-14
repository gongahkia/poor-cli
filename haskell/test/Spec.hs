{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import qualified Data.Map.Strict as Map
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
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
