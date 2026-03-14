{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import qualified Data.Map.Strict as Map
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Seuss.Core.Diff
import Seuss.Core.Eval
import Seuss.Core.Validation
import Seuss.Import.CSV
import Seuss.Lang.Parser
import Seuss.Model.Types
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
