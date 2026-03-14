{-# LANGUAGE OverloadedStrings #-}

module Seuss.Tooling.LSP
    ( CompletionItem(..)
    , getCompletions
    , getDiagnostics
    , getHoverInfo
    , runLspServer
    ) where

import qualified Data.Aeson as Aeson
import Data.Aeson ((.=))
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KeyMap
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as BS8
import qualified Data.ByteString.Lazy as BL
import qualified Data.ByteString.Lazy.Char8 as BL8
import Data.Char (isAlphaNum)
import Data.IORef
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Vector as Vector
import Seuss.Core.Eval
import Seuss.Core.Validation
import Seuss.Lang.Parser
import Seuss.Model.Types
import Seuss.Tooling.Syntax
import System.IO (BufferMode(NoBuffering), Handle, hFlush, hGetLine, hSetBuffering, stdin, stdout)

data CompletionItem = CompletionItem
    { completionLabel :: Text
    , completionDetail :: Text
    }
    deriving (Eq, Show)

data LspMessage = LspMessage
    { messageId :: Maybe Aeson.Value
    , messageMethod :: Maybe Text
    , messageParams :: Maybe Aeson.Value
    }

getCompletions :: Text -> [CompletionItem]
getCompletions prefix =
    [ CompletionItem keyword "keyword"
    | keyword <- syntaxKeywords
    , T.toLower prefix `T.isPrefixOf` T.toLower keyword
    ]

getDiagnostics :: FilePath -> Text -> [Diagnostic]
getDiagnostics file input =
    case parseProgram file input of
        Left diags -> diags
        Right program ->
            case evalProgram program of
                Left diag -> [diag]
                Right world -> validateWorld world

getHoverInfo :: FilePath -> Text -> Text -> Maybe Text
getHoverInfo file input word =
    case parseProgram file input of
        Left _ -> Nothing
        Right program ->
            case evalProgram program of
                Left _ -> Nothing
                Right world ->
                    case Map.lookup word (worldEntities world) of
                        Just entity ->
                            Just $
                                "entity "
                                    <> entityName entity
                                    <> " : "
                                    <> entityType entity
                        Nothing ->
                            case Map.lookup word (worldTimelines world) of
                                Just timeline ->
                                    Just $
                                        "timeline "
                                            <> timelineName timeline
                                            <> " ("
                                            <> T.pack (show (timelineKind timeline))
                                            <> ")"
                                Nothing -> Nothing

runLspServer :: IO ()
runLspServer = do
    hSetBuffering stdin NoBuffering
    hSetBuffering stdout NoBuffering
    documentsRef <- newIORef Map.empty
    loop documentsRef False
  where
    loop documentsRef hasShutdown = do
        maybeMessage <- readLspMessage stdin
        case maybeMessage of
            Nothing -> pure ()
            Just message ->
                case messageMethod message of
                    Just "exit" ->
                        pure ()
                    Just "shutdown" -> do
                        maybe (pure ()) (`writeLspMessage` Aeson.Null) (messageId message)
                        loop documentsRef True
                    Just "initialize" -> do
                        maybe (pure ()) (`writeLspMessage` initializeResult) (messageId message)
                        loop documentsRef hasShutdown
                    Just "initialized" ->
                        loop documentsRef hasShutdown
                    Just "textDocument/didOpen" -> do
                        updateDocument documentsRef message
                        publishDiagnostics documentsRef message
                        loop documentsRef hasShutdown
                    Just "textDocument/didChange" -> do
                        updateDocument documentsRef message
                        publishDiagnostics documentsRef message
                        loop documentsRef hasShutdown
                    Just "textDocument/didClose" -> do
                        closeDocument documentsRef message
                        clearDiagnostics message
                        loop documentsRef hasShutdown
                    Just "textDocument/completion" -> do
                        completionResult <- completionResponse documentsRef message
                        maybe (pure ()) (`writeLspMessage` completionResult) (messageId message)
                        loop documentsRef hasShutdown
                    Just "textDocument/hover" -> do
                        hoverResult <- hoverResponse documentsRef message
                        maybe (pure ()) (`writeLspMessage` hoverResult) (messageId message)
                        loop documentsRef hasShutdown
                    _ ->
                        if hasShutdown
                            then pure ()
                            else loop documentsRef hasShutdown

readLspMessage :: Handle -> IO (Maybe LspMessage)
readLspMessage handle = do
    headers <- readHeaders handle Map.empty
    case Map.lookup "Content-Length" headers >>= readInt of
        Nothing -> pure Nothing
        Just contentLength -> do
            body <- BS.hGet handle contentLength
            pure (Aeson.decodeStrict' body >>= parseMessage)

readHeaders :: Handle -> Map.Map String String -> IO (Map.Map String String)
readHeaders handle headers = do
    rawLine <- hGetLine handle
    let lineValue = stripCarriageReturn rawLine
    if null lineValue
        then pure headers
        else do
            let (headerName, headerValue) = break (== ':') lineValue
                cleanedValue = dropWhile (== ' ') (drop 1 headerValue)
            readHeaders handle (Map.insert headerName cleanedValue headers)

stripCarriageReturn :: String -> String
stripCarriageReturn = reverse . dropWhile (== '\r') . reverse

readInt :: String -> Maybe Int
readInt raw =
    case reads raw of
        [(value, "")] -> Just value
        _ -> Nothing

parseMessage :: Aeson.Value -> Maybe LspMessage
parseMessage (Aeson.Object obj) =
    Just
        LspMessage
            { messageId = lookupValue "id" obj
            , messageMethod =
                case lookupValue "method" obj of
                    Just (Aeson.String methodValue) -> Just methodValue
                    _ -> Nothing
            , messageParams = lookupValue "params" obj
            }
parseMessage _ = Nothing

writeLspMessage :: Aeson.Value -> Aeson.Value -> IO ()
writeLspMessage requestId resultValue =
    sendJson
        ( Aeson.object
            [ "jsonrpc" .= ("2.0" :: Text)
            , "id" .= requestId
            , "result" .= resultValue
            ]
        )

sendNotification :: Text -> Aeson.Value -> IO ()
sendNotification methodName paramsValue =
    sendJson
        ( Aeson.object
            [ "jsonrpc" .= ("2.0" :: Text)
            , "method" .= methodName
            , "params" .= paramsValue
            ]
        )

sendJson :: Aeson.Value -> IO ()
sendJson value = do
    let payload = Aeson.encode value
        header = BS8.pack ("Content-Length: " <> show (BL.length payload) <> "\r\n\r\n")
    BS8.putStr header
    BL8.putStr payload
    hFlush stdout

initializeResult :: Aeson.Value
initializeResult =
    Aeson.object
        [ "capabilities"
            .= Aeson.object
                [ "textDocumentSync"
                    .= Aeson.object
                        [ "openClose" .= True
                        , "change" .= (1 :: Int)
                        ]
                , "hoverProvider" .= True
                , "completionProvider"
                    .= Aeson.object
                        [ "resolveProvider" .= False
                        , "triggerCharacters" .= [".", ":" :: Text]
                        ]
                ]
        ]

updateDocument :: IORef (Map.Map Text Text) -> LspMessage -> IO ()
updateDocument documentsRef message =
    case messageParams message >>= asObject of
        Nothing -> pure ()
        Just paramsObj ->
            case extractOpenedDocument paramsObj of
                Just (uriValue, textValue) ->
                    modifyIORef' documentsRef (Map.insert uriValue textValue)
                Nothing ->
                    case (lookupObject "textDocument" paramsObj, lookupChanges paramsObj) of
                        (Just textDocObj, Just changes) ->
                            case (lookupText "uri" textDocObj, extractChangedText changes) of
                                (Just uriValue, Just textValue) ->
                                    modifyIORef' documentsRef (Map.insert uriValue textValue)
                                _ ->
                                    pure ()
                        _ ->
                            pure ()

closeDocument :: IORef (Map.Map Text Text) -> LspMessage -> IO ()
closeDocument documentsRef message =
    case messageParams message >>= asObject >>= lookupObject "textDocument" >>= lookupText "uri" of
        Nothing -> pure ()
        Just uriValue ->
            modifyIORef' documentsRef (Map.delete uriValue)

publishDiagnostics :: IORef (Map.Map Text Text) -> LspMessage -> IO ()
publishDiagnostics documentsRef message =
    case messageParams message >>= asObject >>= lookupObject "textDocument" >>= lookupText "uri" of
        Nothing -> pure ()
        Just uriValue -> do
            documents <- readIORef documentsRef
            case Map.lookup uriValue documents of
                Nothing -> pure ()
                Just textValue ->
                    sendNotification
                        "textDocument/publishDiagnostics"
                        ( Aeson.object
                            [ "uri" .= uriValue
                            , "diagnostics" .= map diagnosticToLsp (getDiagnostics (uriToFilePath uriValue) textValue)
                            ]
                        )

clearDiagnostics :: LspMessage -> IO ()
clearDiagnostics message =
    case messageParams message >>= asObject >>= lookupObject "textDocument" >>= lookupText "uri" of
        Nothing -> pure ()
        Just uriValue ->
            sendNotification
                "textDocument/publishDiagnostics"
                ( Aeson.object
                    [ "uri" .= uriValue
                    , "diagnostics" .= ([] :: [Aeson.Value])
                    ]
                )

completionResponse :: IORef (Map.Map Text Text) -> LspMessage -> IO Aeson.Value
completionResponse documentsRef message = do
    documents <- readIORef documentsRef
    pure $
        case completionContext documents message of
            Nothing -> Aeson.toJSON ([] :: [Aeson.Value])
            Just prefixValue ->
                Aeson.toJSON
                    [ Aeson.object
                        [ "label" .= completionLabel item
                        , "detail" .= completionDetail item
                        ]
                    | item <- getCompletions prefixValue
                    ]

hoverResponse :: IORef (Map.Map Text Text) -> LspMessage -> IO Aeson.Value
hoverResponse documentsRef message = do
    documents <- readIORef documentsRef
    pure $
        case hoverContext documents message of
            Nothing -> Aeson.Null
            Just (uriValue, sourceText, hoveredWord) ->
                maybe
                    Aeson.Null
                    (\infoText -> Aeson.object ["contents" .= Aeson.object ["kind" .= ("plaintext" :: Text), "value" .= infoText]])
                    (getHoverInfo (uriToFilePath uriValue) sourceText hoveredWord)

completionContext :: Map.Map Text Text -> LspMessage -> Maybe Text
completionContext documents message = do
    paramsObj <- messageParams message >>= asObject
    textDocObj <- lookupObject "textDocument" paramsObj
    uriValue <- lookupText "uri" textDocObj
    sourceText <- Map.lookup uriValue documents
    positionObj <- lookupObject "position" paramsObj
    lineIndex <- lookupInt "line" positionObj
    charIndex <- lookupInt "character" positionObj
    pure (prefixAtPosition sourceText lineIndex charIndex)

hoverContext :: Map.Map Text Text -> LspMessage -> Maybe (Text, Text, Text)
hoverContext documents message = do
    paramsObj <- messageParams message >>= asObject
    textDocObj <- lookupObject "textDocument" paramsObj
    uriValue <- lookupText "uri" textDocObj
    sourceText <- Map.lookup uriValue documents
    positionObj <- lookupObject "position" paramsObj
    lineIndex <- lookupInt "line" positionObj
    charIndex <- lookupInt "character" positionObj
    hoveredWord <- wordAtPosition sourceText lineIndex charIndex
    pure (uriValue, sourceText, hoveredWord)

prefixAtPosition :: Text -> Int -> Int -> Text
prefixAtPosition sourceText lineIndex charIndex =
    case safeIndex lineIndex (T.lines sourceText) of
        Nothing -> ""
        Just lineValue ->
            T.reverse (T.takeWhile isWordChar (T.reverse (T.take charIndex lineValue)))

wordAtPosition :: Text -> Int -> Int -> Maybe Text
wordAtPosition sourceText lineIndex charIndex = do
    lineValue <- safeIndex lineIndex (T.lines sourceText)
    let (leftPart, rightPart) = T.splitAt charIndex lineValue
        leftWord = T.reverse (T.takeWhile isWordChar (T.reverse leftPart))
        rightWord = T.takeWhile isWordChar rightPart
        wordValue = leftWord <> rightWord
    if T.null wordValue then Nothing else Just wordValue

isWordChar :: Char -> Bool
isWordChar charValue = isAlphaNum charValue || charValue == '_'

diagnosticToLsp :: Diagnostic -> Aeson.Value
diagnosticToLsp diagnostic =
    Aeson.object
        [ "range"
            .= Aeson.object
                [ "start" .= Aeson.object ["line" .= (0 :: Int), "character" .= (0 :: Int)]
                , "end" .= Aeson.object ["line" .= (0 :: Int), "character" .= (1 :: Int)]
                ]
        , "severity" .= if diagnosticLevel diagnostic == DiagnosticError then (1 :: Int) else (2 :: Int)
        , "source" .= diagnosticSource diagnostic
        , "message" .= diagnosticMessage diagnostic
        ]

extractOpenedDocument :: Aeson.Object -> Maybe (Text, Text)
extractOpenedDocument paramsObj = do
    textDocObj <- lookupObject "textDocument" paramsObj
    uriValue <- lookupText "uri" textDocObj
    textValue <- lookupText "text" textDocObj
    pure (uriValue, textValue)

extractChangedText :: Vector.Vector Aeson.Value -> Maybe Text
extractChangedText changes =
    case Vector.toList changes of
        Aeson.Object changeObj : _ -> lookupText "text" changeObj
        _ -> Nothing

lookupChanges :: Aeson.Object -> Maybe (Vector.Vector Aeson.Value)
lookupChanges obj =
    case lookupValue "contentChanges" obj of
        Just (Aeson.Array values) -> Just values
        _ -> Nothing

lookupObject :: Text -> Aeson.Object -> Maybe Aeson.Object
lookupObject keyName obj =
    case lookupValue keyName obj of
        Just (Aeson.Object nestedObj) -> Just nestedObj
        _ -> Nothing

lookupText :: Text -> Aeson.Object -> Maybe Text
lookupText keyName obj =
    case lookupValue keyName obj of
        Just (Aeson.String textValue) -> Just textValue
        _ -> Nothing

lookupInt :: Text -> Aeson.Object -> Maybe Int
lookupInt keyName obj =
    case lookupValue keyName obj of
        Just (Aeson.Number numberValue) -> toInt numberValue
        _ -> Nothing

lookupValue :: Text -> Aeson.Object -> Maybe Aeson.Value
lookupValue keyName obj = KeyMap.lookup (Key.fromText keyName) obj

asObject :: Aeson.Value -> Maybe Aeson.Object
asObject (Aeson.Object obj) = Just obj
asObject _ = Nothing

toInt :: (Eq a, RealFrac a) => a -> Maybe Int
toInt numberValue =
    let intValue = floor numberValue
     in if fromIntegral intValue == numberValue
            then Just intValue
            else Nothing

uriToFilePath :: Text -> FilePath
uriToFilePath uriValue =
    T.unpack (fromMaybePrefix uriValue (T.stripPrefix "file://" uriValue))

fromMaybePrefix :: a -> Maybe a -> a
fromMaybePrefix fallback maybeValue =
    case maybeValue of
        Just value -> value
        Nothing -> fallback

safeIndex :: Int -> [a] -> Maybe a
safeIndex indexValue values
    | indexValue < 0 = Nothing
    | otherwise =
        case drop indexValue values of
            [] -> Nothing
            value : _ -> Just value
