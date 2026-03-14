{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Control.Monad (filterM, unless, when)
import Data.List (isSuffixOf)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.IO as TIO
import Options.Applicative (execParser)
import Seuss.CLI.Options
import Seuss.Core.Diff
import Seuss.Core.Eval
import Seuss.Core.Validation
import Seuss.Import.CSV
import Seuss.Import.GEDCOM
import Seuss.Import.JSONLD
import Seuss.Lang.AST (Program(..), Stmt)
import Seuss.Lang.Parser
import Seuss.Model.Types
import Seuss.Render.Layout
import Seuss.Render.SVG
import Seuss.TUI.App
import System.Directory
import System.Exit (exitFailure)
import System.FilePath ((</>), takeBaseName, takeDirectory, takeExtension, takeFileName, replaceExtension)
import System.IO (hFlush, stdout)

data LoadedWorld = LoadedWorld
    { loadedWorld :: World
    , loadedDiagnostics :: [Diagnostic]
    , loadedProgram :: Program
    }

data ReplState = ReplState
    { replProgram :: [Stmt]
    , replWorld :: World
    , replDiagnostics :: [Diagnostic]
    }

main :: IO ()
main = do
    options <- execParser optionsParserInfo
    when (optVerbose options) $
        putStrLn "Running Haskell Seuss implementation"
    runCommand options

runCommand :: Options -> IO ()
runCommand options =
    case optCommand options of
        CommandRun filePath -> do
            loaded <- loadSeussFile filePath
            reportDiagnostics (loadedDiagnostics loaded)
            runSeussTui filePath (loadedWorld loaded)
        CommandExport exportOpts -> runExport exportOpts
        CommandCheck filePath -> runCheck filePath
        CommandDiff leftPath rightPath -> runDiff leftPath rightPath
        CommandImport importOpts -> runImport importOpts
        CommandRepl -> runRepl

runExport :: ExportOptions -> IO ()
runExport exportOptions = do
    loaded <- loadSeussFile (exportFile exportOptions)
    case exportFormat exportOptions of
        ExportSvg -> do
            let svgOptions =
                    defaultSvgOptions
                        { svgWidth = fromMaybe (svgWidth defaultSvgOptions) (exportWidth exportOptions)
                        , svgHeight = fromMaybe (svgHeight defaultSvgOptions) (exportHeight exportOptions)
                        , svgTitle = T.pack (takeBaseName (exportFile exportOptions))
                        }
                outputPath = fromMaybe (replaceExtension (exportFile exportOptions) "svg") (exportOutput exportOptions)
                svgDocument = renderSvg svgOptions (computeLayout (loadedWorld loaded))
            TIO.writeFile outputPath svgDocument
            reportDiagnostics (loadedDiagnostics loaded)
            putStrLn ("Wrote " <> outputPath)
        ExportPng ->
            failUnsupported "PNG export is not implemented yet in the Haskell rewrite; SVG is available now."
        ExportPdf ->
            failUnsupported "PDF export is not implemented yet in the Haskell rewrite; SVG is available now."

runCheck :: FilePath -> IO ()
runCheck filePath = do
    loaded <- loadSeussFile filePath
    if null (loadedDiagnostics loaded)
        then putStrLn "OK"
        else do
            reportDiagnostics (loadedDiagnostics loaded)
            when (hasErrors (loadedDiagnostics loaded)) exitFailure

runDiff :: FilePath -> FilePath -> IO ()
runDiff leftPath rightPath = do
    leftWorldValue <- loadSeussFile leftPath
    rightWorldValue <- loadSeussFile rightPath
    TIO.putStrLn (diffWorlds (loadedWorld leftWorldValue) (loadedWorld rightWorldValue))

runImport :: ImportOptions -> IO ()
runImport importOptions = do
    input <- TIO.readFile (importFile importOptions)
    let imported =
            case importFormat importOptions of
                ImportCsv -> importCsvToSeuss input
                ImportGedcom -> importGedcomToSeuss input
                ImportJsonld -> importJsonLdToSeuss input
    case imported of
        Left diags -> do
            reportDiagnostics diags
            exitFailure
        Right seussSource ->
            case importOutput importOptions of
                Nothing -> TIO.putStrLn seussSource
                Just outputPath -> TIO.writeFile outputPath seussSource

runRepl :: IO ()
runRepl = do
    putStrLn "Seuss Haskell REPL"
    putStrLn ":load <path> | :files | :world | :entities | :rels | :validate | :quit"
    replLoop initialReplState

initialReplState :: ReplState
initialReplState =
    ReplState
        { replProgram = []
        , replWorld = emptyWorld
        , replDiagnostics = []
        }

replLoop :: ReplState -> IO ()
replLoop state = do
    putStr "seuss> "
    hFlush stdout
    input <- getLine
    case words input of
        [] -> replLoop state
        [":quit"] -> pure ()
        [":q"] -> pure ()
        [":files"] -> do
            files <- discoverSeussFiles "."
            mapM_ putStrLn files
            replLoop state
        [":world"] -> do
            TIO.putStrLn (renderWorldSummary (replWorld state))
            replLoop state
        [":entities"] -> do
            mapM_ (TIO.putStrLn . renderEntitySummary) (Map.elems (worldEntities (replWorld state)))
            replLoop state
        [":rels"] -> do
            mapM_ (TIO.putStrLn . renderRelationshipSummary) (worldRelationships (replWorld state))
            replLoop state
        [":validate"] -> do
            reportDiagnostics (validateWorld (replWorld state))
            replLoop state
        [":load", filePath] -> do
            loaded <- loadSeussFile filePath
            reportDiagnostics (loadedDiagnostics loaded)
            replLoop
                ReplState
                    { replProgram = let Program statements = loadedProgram loaded in statements
                    , replWorld = loadedWorld loaded
                    , replDiagnostics = loadedDiagnostics loaded
                    }
        _ ->
            case parseStatement "<repl>" (T.pack input) of
                Left diags -> do
                    reportDiagnostics diags
                    replLoop state
                Right statement ->
                    case evalProgram (Program (replProgram state ++ [statement])) of
                        Left diag -> do
                            reportDiagnostics [diag]
                            replLoop state
                        Right worldValue -> do
                            let newDiagnostics = validateWorld worldValue
                            reportDiagnostics newDiagnostics
                            replLoop
                                state
                                    { replProgram = replProgram state ++ [statement]
                                    , replWorld = worldValue
                                    , replDiagnostics = newDiagnostics
                                    }

loadSeussFile :: FilePath -> IO LoadedWorld
loadSeussFile filePath = do
    source <- TIO.readFile filePath
    case parseProgram filePath source of
        Left diags -> do
            reportDiagnostics diags
            exitFailure
        Right program ->
            case evalProgram program of
                Left diag -> do
                    reportDiagnostics [diag]
                    exitFailure
                Right worldValue -> do
                    let diagnostics = validateWorld worldValue
                    pure
                        LoadedWorld
                            { loadedWorld = worldValue
                            , loadedDiagnostics = diagnostics
                            , loadedProgram = program
                            }

discoverSeussFiles :: FilePath -> IO [FilePath]
discoverSeussFiles root = do
    entries <- listDirectory root
    let filtered = filter (`notElem` [".git", "target", "dist-newstyle"]) entries
    paths <- traverse toPath filtered
    pure (concat paths)
  where
    toPath entry = do
        let path = root </> entry
        isDir <- doesDirectoryExist path
        if isDir
            then discoverSeussFiles path
            else pure [path | ".seuss" `isSuffixOf` path]

renderWorldSummary :: World -> Text
renderWorldSummary worldValue =
    T.unlines
        [ "timelines: " <> T.pack (show (Map.size (worldTimelines worldValue)))
        , "entities: " <> T.pack (show (Map.size (worldEntities worldValue)))
        , "relationships: " <> T.pack (show (length (worldRelationships worldValue)))
        , "types: " <> T.pack (show (Map.size (worldTypes worldValue)))
        ]

renderEntitySummary :: Entity -> Text
renderEntitySummary entity =
    entityName entity
        <> " : "
        <> entityType entity
        <> " appearances="
        <> T.pack (show (length (entityAppearances entity)))

renderRelationshipSummary :: Relationship -> Text
renderRelationshipSummary relationship =
    relSource relationship
        <> " "
        <> maybe "-->" (\labelValue -> "-[\"" <> labelValue <> "\"]->") (relLabel relationship)
        <> " "
        <> relTarget relationship

reportDiagnostics :: [Diagnostic] -> IO ()
reportDiagnostics = mapM_ (TIO.putStrLn . renderDiagnostic)

hasErrors :: [Diagnostic] -> Bool
hasErrors = any ((== DiagnosticError) . diagnosticLevel)

failUnsupported :: String -> IO ()
failUnsupported message = do
    putStrLn message
    exitFailure
