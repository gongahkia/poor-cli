{-# LANGUAGE OverloadedStrings #-}

module Seuss.CLI.Options
    ( Command(..)
    , ExportFormat(..)
    , ExportOptions(..)
    , ImportFormat(..)
    , ImportOptions(..)
    , Options(..)
    , optionsParserInfo
    ) where

import Data.Char (toLower)
import Data.Text (Text)
import qualified Data.Text as T
import Options.Applicative

data ExportFormat
    = ExportSvg
    | ExportPng
    | ExportPdf
    deriving (Eq, Show)

data ImportFormat
    = ImportCsv
    | ImportGedcom
    | ImportJsonld
    deriving (Eq, Show)

data ExportOptions = ExportOptions
    { exportFile :: FilePath
    , exportFormat :: ExportFormat
    , exportOutput :: Maybe FilePath
    , exportWidth :: Maybe Int
    , exportHeight :: Maybe Int
    , exportDpi :: Maybe Int
    }
    deriving (Eq, Show)

data ImportOptions = ImportOptions
    { importFile :: FilePath
    , importFormat :: ImportFormat
    , importOutput :: Maybe FilePath
    }
    deriving (Eq, Show)

data Command
    = CommandRun FilePath
    | CommandExport ExportOptions
    | CommandCheck FilePath
    | CommandDiff FilePath FilePath
    | CommandImport ImportOptions
    | CommandRepl
    | CommandLsp
    deriving (Eq, Show)

data Options = Options
    { optVerbose :: Bool
    , optConfig :: Maybe FilePath
    , optTheme :: Maybe Text
    , optCommand :: Command
    }
    deriving (Eq, Show)

optionsParserInfo :: ParserInfo Options
optionsParserInfo =
    info
        (helper <*> optionsParser)
        (fullDesc <> progDesc "Seuss timeline DSL and terminal explorer")

optionsParser :: Parser Options
optionsParser =
    Options
        <$> switch (long "verbose" <> help "Enable verbose logging")
        <*> optional (strOption (long "config" <> metavar "PATH" <> help "Path to TOML config"))
        <*> optional (T.pack <$> strOption (long "theme" <> metavar "NAME" <> help "Theme name or TOML path"))
        <*> hsubparser
            ( command "run" (info runParser (progDesc "Run the analytical terminal UI"))
                <> command "export" (info exportParser (progDesc "Export a .seuss file"))
                <> command "check" (info checkParser (progDesc "Parse and validate a .seuss file"))
                <> command "diff" (info diffParser (progDesc "Semantic diff of two .seuss files"))
                <> command "import" (info importParser (progDesc "Import external data into .seuss"))
                <> command "repl" (info replParser (progDesc "Interactive REPL"))
                <> command "lsp" (info lspParser (progDesc "Run the stdio language server"))
            )

runParser :: Parser Command
runParser =
    CommandRun
        <$> argument str (metavar "FILE")

exportParser :: Parser Command
exportParser =
    CommandExport
        <$> ( ExportOptions
                <$> argument str (metavar "FILE")
                <*> option
                    (eitherReader parseExportFormat)
                    (short 'f' <> long "format" <> value ExportSvg <> metavar "FORMAT" <> help "svg | png | pdf")
                <*> optional (strOption (short 'o' <> long "output" <> metavar "PATH"))
                <*> optional (option auto (long "width" <> metavar "PIXELS"))
                <*> optional (option auto (long "height" <> metavar "PIXELS"))
                <*> optional (option auto (long "dpi" <> metavar "DPI"))
            )

checkParser :: Parser Command
checkParser =
    CommandCheck
        <$> argument str (metavar "FILE")

diffParser :: Parser Command
diffParser =
    CommandDiff
        <$> argument str (metavar "FILE1")
        <*> argument str (metavar "FILE2")

importParser :: Parser Command
importParser =
    CommandImport
        <$> ( ImportOptions
                <$> argument str (metavar "FILE")
                <*> option
                    (eitherReader parseImportFormat)
                    (long "from" <> value ImportCsv <> metavar "FORMAT" <> help "csv | gedcom | jsonld")
                <*> optional (strOption (short 'o' <> long "output" <> metavar "PATH"))
            )

replParser :: Parser Command
replParser = pure CommandRepl

lspParser :: Parser Command
lspParser = pure CommandLsp

parseExportFormat :: String -> Either String ExportFormat
parseExportFormat raw =
    case map toLower raw of
        "svg" -> Right ExportSvg
        "png" -> Right ExportPng
        "pdf" -> Right ExportPdf
        other -> Left ("unknown export format: " <> other)

parseImportFormat :: String -> Either String ImportFormat
parseImportFormat raw =
    case map toLower raw of
        "csv" -> Right ImportCsv
        "gedcom" -> Right ImportGedcom
        "jsonld" -> Right ImportJsonld
        other -> Left ("unknown import format: " <> other)
