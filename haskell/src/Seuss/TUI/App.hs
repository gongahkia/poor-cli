{-# LANGUAGE OverloadedStrings #-}

module Seuss.TUI.App
    ( runSeussTui
    ) where

import Brick
import qualified Brick.Main as M
import Brick.Util (fg, on)
import qualified Graphics.Vty as V
import Data.Char (digitToInt)
import Data.List (nub, sort)
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Core.Validation
import Seuss.Model.Types
import Seuss.Render.Layout

data Name = Root
    deriving (Eq, Ord, Show)

data Pane
    = PaneTimelines
    | PaneEntities
    | PaneRelationships
    | PaneDiagnostics
    deriving (Eq, Show, Enum, Bounded)

data Mode
    = ModeNormal
    | ModeSearch
    deriving (Eq, Show)

data AppSnapshot = AppSnapshot
    { snapshotPane :: Pane
    , snapshotTimelineIndex :: Int
    , snapshotEntityIndex :: Int
    , snapshotRelationshipIndex :: Int
    , snapshotDiagnosticIndex :: Int
    , snapshotSearch :: Text
    , snapshotTypeFilter :: Maybe Text
    , snapshotNeighborhoodOnly :: Bool
    , snapshotCompareTimeline :: Maybe Text
    }

data AppState = AppState
    { appFilePath :: FilePath
    , appWorld :: World
    , appLayout :: Layout
    , appDiagnostics :: [Diagnostic]
    , appPane :: Pane
    , appMode :: Mode
    , appTimelineIndex :: Int
    , appEntityIndex :: Int
    , appRelationshipIndex :: Int
    , appDiagnosticIndex :: Int
    , appSearch :: Text
    , appTypeFilter :: Maybe Text
    , appNeighborhoodOnly :: Bool
    , appCompareTimeline :: Maybe Text
    , appBookmarks :: Map.Map Int Text
    , appUndoStack :: [AppSnapshot]
    , appRedoStack :: [AppSnapshot]
    , appShowHelp :: Bool
    , appStatus :: Text
    }

runSeussTui :: FilePath -> World -> IO ()
runSeussTui filePath world = do
    let initialState =
            AppState
                { appFilePath = filePath
                , appWorld = world
                , appLayout = computeLayout world
                , appDiagnostics = validateWorld world
                , appPane = PaneEntities
                , appMode = ModeNormal
                , appTimelineIndex = 0
                , appEntityIndex = 0
                , appRelationshipIndex = 0
                , appDiagnosticIndex = 0
                , appSearch = ""
                , appTypeFilter = Nothing
                , appNeighborhoodOnly = False
                , appCompareTimeline = Nothing
                , appBookmarks = Map.empty
                , appUndoStack = []
                , appRedoStack = []
                , appShowHelp = False
                , appStatus = "Tab switches panes, / searches, t filters types, n toggles neighborhood mode, q quits"
                }
    _ <- M.defaultMain appDefinition initialState
    pure ()

appDefinition :: App AppState e Name
appDefinition =
    App
        { appDraw = drawUi
        , appChooseCursor = neverShowCursor
        , appHandleEvent = handleEvent
        , appStartEvent = pure
        , appAttrMap = const attrMapDefinition
        }

drawUi :: AppState -> [Widget Name]
drawUi state =
    [ if appShowHelp state
        then baseWidget <=> drawHelp
        else baseWidget
    ]
  where
    baseWidget =
        vBox
            [ borderWithLabel (withAttr headingAttr (txt "Seuss Haskell TUI")) $
                hBox
                    [ hLimit 32 (drawPane "Timelines" (appPane state == PaneTimelines) timelineRows)
                    , hLimit 48 (drawPane "Entities" (appPane state == PaneEntities) entityRows)
                    , hLimit 36 (drawPane "Relationships" (appPane state == PaneRelationships) relationshipRows)
                    , drawPane "Inspector" (appPane state == PaneDiagnostics) inspectorRows
                    ]
            , drawStatus state
            ]
    timelineRows =
        selectableRows
            (appPane state == PaneTimelines)
            (appTimelineIndex state)
            [ layoutTimelineName timeline <> " [" <> T.pack (show (layoutTimelineKind timeline)) <> "]"
            | timeline <- layoutTimelines (appLayout state)
            ]
    entityRows =
        selectableRows
            (appPane state == PaneEntities)
            (appEntityIndex state)
            [ layoutEntityName entity <> " : " <> layoutEntityType entity
            | entity <- visibleEntities state
            ]
    relationshipRows =
        selectableRows
            (appPane state == PaneRelationships)
            (appRelationshipIndex state)
            [ renderRelationship relationship
            | relationship <- visibleRelationships state
            ]
    inspectorRows = map txtWrap (inspectorText state)

drawPane :: Text -> Bool -> [Widget Name] -> Widget Name
drawPane labelValue active rows =
    borderWithLabel (withAttr headingAttr (txt labelValue)) $
        padAll 1 $
            vBox bodyRows
  where
    bodyRows =
        ( if null rows
            then [withAttr mutedAttr (txt "(empty)")]
            else rows
        )
            ++ [ padTop (Pad 1) $
                    if active
                        then withAttr statusAttr (txt "active")
                        else emptyWidget
               ]

drawStatus :: AppState -> Widget Name
drawStatus state =
    withAttr statusAttr $
        padAll 1 $
            txt $
                "file: "
                    <> T.pack (appFilePath state)
                    <> " | mode: "
                    <> T.pack (show (appMode state))
                    <> " | search: "
                    <> appSearch state
                    <> " | type: "
                    <> fromMaybe "all" (appTypeFilter state)
                    <> " | "
                    <> appStatus state

selectableRows :: Bool -> Int -> [Text] -> [Widget Name]
selectableRows active selectedIndex values =
    zipWith renderRow [0 ..] values
  where
    renderRow rowIndex value
        | active && rowIndex == selectedIndex = withAttr selectedAttr (padRight Max (txt value))
        | otherwise = padRight Max (txt value)

inspectorText :: AppState -> [Text]
inspectorText state =
    timelineDetails
        ++ [""]
        ++ entityDetails
        ++ [""]
        ++ relationshipDetails
        ++ [""]
        ++ compareDetails
        ++ [""]
        ++ diagnosticDetails
  where
    timelineDetails =
        case safeIndex (appTimelineIndex state) (layoutTimelines (appLayout state)) of
            Nothing -> ["Timeline: none"]
            Just timeline ->
                [ "Timeline"
                , "  name: " <> layoutTimelineName timeline
                , "  kind: " <> T.pack (show (layoutTimelineKind timeline))
                , "  start: " <> T.pack (show (layoutTimelineStart timeline))
                , "  end: " <> T.pack (show (layoutTimelineEnd timeline))
                ]
    entityDetails =
        case safeIndex (appEntityIndex state) (visibleEntities state) of
            Nothing -> ["Entity: none"]
            Just entity ->
                let fieldLines =
                        case Map.lookup (layoutEntityName entity) (worldEntities (appWorld state)) of
                            Nothing -> []
                            Just sourceEntity ->
                                [ "  " <> keyValue <> ": " <> T.pack (show value)
                                | (keyValue, value) <- Map.toList (entityFields sourceEntity)
                                ]
                 in [ "Entity"
                    , "  name: " <> layoutEntityName entity
                    , "  type: " <> layoutEntityType entity
                    , "  timeline: " <> layoutEntityTimeline entity
                    ]
                        ++ fieldLines
    relationshipDetails =
        case safeIndex (appRelationshipIndex state) (visibleRelationships state) of
            Nothing -> ["Relationship: none"]
            Just relationship ->
                [ "Relationship"
                , "  " <> renderRelationship relationship
                ]
    compareDetails =
        case compareSummary state of
            [] -> ["Compare: disabled"]
            linesValue -> "Compare" : map ("  " <>) linesValue
    diagnosticDetails =
        case safeIndex (appDiagnosticIndex state) (appDiagnostics state) of
            Nothing -> ["Diagnostics", "  none"]
            Just diagnostic ->
                [ "Diagnostic"
                , "  " <> renderDiagnostic diagnostic
                ]

handleEvent :: AppState -> BrickEvent Name e -> EventM Name (Next AppState)
handleEvent state (VtyEvent eventValue) =
    case appMode state of
        ModeSearch ->
            case eventValue of
                V.EvKey V.KEsc [] -> M.continue (exitSearch state)
                V.EvKey V.KBS [] -> M.continue (searchBackspace state)
                V.EvKey V.KEnter [] -> M.continue (exitSearch state)
                V.EvKey (V.KChar charValue) [] -> M.continue (searchAppend charValue state)
                _ -> M.continue state
        ModeNormal ->
            case eventValue of
                V.EvKey (V.KChar 'q') [] -> M.halt state
                V.EvKey (V.KChar '\t') [] -> M.continue (advancePane state)
                V.EvKey V.KUp [] -> M.continue (moveSelection (-1) state)
                V.EvKey (V.KChar 'k') [] -> M.continue (moveSelection (-1) state)
                V.EvKey V.KDown [] -> M.continue (moveSelection 1 state)
                V.EvKey (V.KChar 'j') [] -> M.continue (moveSelection 1 state)
                V.EvKey (V.KChar '/') [] ->
                    M.continue (recordHistory state){appMode = ModeSearch, appStatus = "Search mode"}
                V.EvKey (V.KChar 't') [] -> M.continue (cycleTypeFilter state)
                V.EvKey (V.KChar 'n') [] -> M.continue (toggleNeighborhood state)
                V.EvKey (V.KChar '?') [] -> M.continue state{appShowHelp = not (appShowHelp state)}
                V.EvKey (V.KChar 'c') [] -> M.continue (cycleCompareTimeline state)
                V.EvKey (V.KChar 'b') [] -> M.continue (saveBookmark state)
                V.EvKey (V.KChar 'u') [] -> M.continue (undoState state)
                V.EvKey (V.KChar 'y') [] -> M.continue (redoState state)
                V.EvKey (V.KChar keyValue) []
                    | keyValue >= '1' && keyValue <= '9' ->
                        M.continue (loadBookmark (digitToInt keyValue) state)
                _ -> M.continue state
handleEvent state _ = M.continue state

advancePane :: AppState -> AppState
advancePane state =
    (recordHistory state)
        { appPane =
            case appPane state of
                PaneTimelines -> PaneEntities
                PaneEntities -> PaneRelationships
                PaneRelationships -> PaneDiagnostics
                PaneDiagnostics -> PaneTimelines
        , appStatus = "Switched pane"
        }

moveSelection :: Int -> AppState -> AppState
moveSelection delta state =
    let state' = recordHistory state
     in case appPane state of
        PaneTimelines ->
            state'
                { appTimelineIndex =
                    boundedMove delta (appTimelineIndex state) (layoutTimelines (appLayout state))
                }
        PaneEntities ->
            state'
                { appEntityIndex =
                    boundedMove delta (appEntityIndex state) (visibleEntities state)
                }
        PaneRelationships ->
            state'
                { appRelationshipIndex =
                    boundedMove delta (appRelationshipIndex state) (visibleRelationships state)
                }
        PaneDiagnostics ->
            state'
                { appDiagnosticIndex =
                    boundedMove delta (appDiagnosticIndex state) (appDiagnostics state)
                }

boundedMove :: Int -> Int -> [a] -> Int
boundedMove delta currentIndex values
    | null values = 0
    | otherwise = max 0 (min (length values - 1) (currentIndex + delta))

visibleEntities :: AppState -> [LayoutEntity]
visibleEntities state =
    filter entityVisible (layoutEntities (appLayout state))
  where
    searchValue = T.toLower (appSearch state)
    entityVisible entity =
        searchMatches entity && typeMatches entity
    searchMatches entity =
        T.null searchValue
            || searchValue `T.isInfixOf` T.toLower (layoutEntityName entity)
            || searchValue `T.isInfixOf` T.toLower (layoutEntityType entity)
    typeMatches entity =
        maybe True (== layoutEntityType entity) (appTypeFilter state)

visibleRelationships :: AppState -> [LayoutRelationship]
visibleRelationships state
    | appNeighborhoodOnly state =
        case safeIndex (appEntityIndex state) (visibleEntities state) of
            Nothing -> []
            Just entity ->
                filter
                    (\relationship -> layoutRelSource relationship == layoutEntityName entity || layoutRelTarget relationship == layoutEntityName entity)
                    allRelationships
    | otherwise = allRelationships
  where
    allRelationships = layoutRelationships (appLayout state)

renderRelationship :: LayoutRelationship -> Text
renderRelationship relationship =
    layoutRelSource relationship
        <> " "
        <> maybe "-->" (\labelValue -> "-[" <> labelValue <> "]->") (layoutRelLabel relationship)
        <> " "
        <> layoutRelTarget relationship

cycleTypeFilter :: AppState -> AppState
cycleTypeFilter state =
    let options = Nothing : map Just (sort (nub [layoutEntityType entity | entity <- layoutEntities (appLayout state)]))
        currentIndex = fromMaybe 0 (lookupIndex (appTypeFilter state) options)
        nextIndex = (currentIndex + 1) `mod` length options
        nextFilter = fromMaybe Nothing (safeIndex nextIndex options)
     in (recordHistory state)
            { appTypeFilter = nextFilter
            , appEntityIndex = 0
            , appStatus = "Cycled type filter"
            }

toggleNeighborhood :: AppState -> AppState
toggleNeighborhood state =
    (recordHistory state)
        { appNeighborhoodOnly = not (appNeighborhoodOnly state)
        , appRelationshipIndex = 0
        , appStatus = "Toggled relationship neighborhood mode"
        }

exitSearch :: AppState -> AppState
exitSearch state =
    state
        { appMode = ModeNormal
        , appStatus = "Exited search mode"
        }

searchBackspace :: AppState -> AppState
searchBackspace state =
    case appMode state of
        ModeNormal -> state
        ModeSearch ->
            (recordHistory state)
                { appSearch =
                    if T.null (appSearch state)
                        then ""
                        else T.init (appSearch state)
                , appEntityIndex = 0
                }

searchAppend :: Char -> AppState -> AppState
searchAppend charValue state =
    case appMode state of
        ModeNormal -> state
        ModeSearch ->
            (recordHistory state)
                { appSearch = appSearch state <> T.singleton charValue
                , appEntityIndex = 0
                , appStatus = "Filtering entities"
                }

recordHistory :: AppState -> AppState
recordHistory state =
    state
        { appUndoStack = snapshotState state : appUndoStack state
        , appRedoStack = []
        }

snapshotState :: AppState -> AppSnapshot
snapshotState state =
    AppSnapshot
        { snapshotPane = appPane state
        , snapshotTimelineIndex = appTimelineIndex state
        , snapshotEntityIndex = appEntityIndex state
        , snapshotRelationshipIndex = appRelationshipIndex state
        , snapshotDiagnosticIndex = appDiagnosticIndex state
        , snapshotSearch = appSearch state
        , snapshotTypeFilter = appTypeFilter state
        , snapshotNeighborhoodOnly = appNeighborhoodOnly state
        , snapshotCompareTimeline = appCompareTimeline state
        }

restoreSnapshot :: AppSnapshot -> AppState -> AppState
restoreSnapshot snapshot state =
    state
        { appPane = snapshotPane snapshot
        , appTimelineIndex = snapshotTimelineIndex snapshot
        , appEntityIndex = snapshotEntityIndex snapshot
        , appRelationshipIndex = snapshotRelationshipIndex snapshot
        , appDiagnosticIndex = snapshotDiagnosticIndex snapshot
        , appSearch = snapshotSearch snapshot
        , appTypeFilter = snapshotTypeFilter snapshot
        , appNeighborhoodOnly = snapshotNeighborhoodOnly snapshot
        , appCompareTimeline = snapshotCompareTimeline snapshot
        }

undoState :: AppState -> AppState
undoState state =
    case appUndoStack state of
        [] -> state{appStatus = "Nothing to undo"}
        snapshot : rest ->
            (restoreSnapshot snapshot state)
                { appUndoStack = rest
                , appRedoStack = snapshotState state : appRedoStack state
                , appStatus = "Undid the last view change"
                }

redoState :: AppState -> AppState
redoState state =
    case appRedoStack state of
        [] -> state{appStatus = "Nothing to redo"}
        snapshot : rest ->
            (restoreSnapshot snapshot state)
                { appRedoStack = rest
                , appUndoStack = snapshotState state : appUndoStack state
                , appStatus = "Redid the last view change"
                }

saveBookmark :: AppState -> AppState
saveBookmark state =
    case safeIndex (appEntityIndex state) (visibleEntities state) of
        Nothing -> state{appStatus = "No visible entity to bookmark"}
        Just entity ->
            let nextSlot = head ([slot | slot <- [1 .. 9], Map.notMember slot (appBookmarks state)] ++ [1])
             in state
                    { appBookmarks = Map.insert nextSlot (layoutEntityName entity) (appBookmarks state)
                    , appStatus = "Saved bookmark " <> T.pack (show nextSlot) <> " for " <> layoutEntityName entity
                    }

loadBookmark :: Int -> AppState -> AppState
loadBookmark slot state =
    case Map.lookup slot (appBookmarks state) of
        Nothing -> state{appStatus = "No bookmark in slot " <> T.pack (show slot)}
        Just entityNameValue ->
            case lookupIndexBy (\entity -> layoutEntityName entity == entityNameValue) (visibleEntities state) of
                Nothing -> state{appStatus = "Bookmarked entity is not visible under current filters"}
                Just indexValue ->
                    (recordHistory state)
                        { appPane = PaneEntities
                        , appEntityIndex = indexValue
                        , appStatus = "Loaded bookmark " <> T.pack (show slot)
                        }

cycleCompareTimeline :: AppState -> AppState
cycleCompareTimeline state =
    case layoutTimelines (appLayout state) of
        [] -> state{appStatus = "No timelines available for comparison"}
        timelinesValue ->
            let names = map layoutTimelineName timelinesValue
                nextName =
                    case appCompareTimeline state of
                        Nothing -> Just (head names)
                        Just current ->
                            safeIndex 0 (drop 1 (dropWhile (/= current) names) ++ names)
             in (recordHistory state)
                    { appCompareTimeline = nextName
                    , appStatus = "Updated timeline comparison target"
                    }

compareSummary :: AppState -> [Text]
compareSummary state =
    case (safeIndex (appTimelineIndex state) (layoutTimelines (appLayout state)), appCompareTimeline state) of
        (Just currentTimeline, Just compareName) ->
            let currentEntities =
                    sort
                        [ layoutEntityName entity
                        | entity <- layoutEntities (appLayout state)
                        , layoutEntityTimeline entity == layoutTimelineName currentTimeline
                        ]
                compareEntities =
                    sort
                        [ layoutEntityName entity
                        | entity <- layoutEntities (appLayout state)
                        , layoutEntityTimeline entity == compareName
                        ]
                onlyCurrent = filter (`notElem` compareEntities) currentEntities
                onlyCompare = filter (`notElem` currentEntities) compareEntities
             in [ "current: " <> layoutTimelineName currentTimeline
                , "against: " <> compareName
                , "only current: " <> renderList onlyCurrent
                , "only compare: " <> renderList onlyCompare
                ]
        _ -> []

renderList :: [Text] -> Text
renderList [] = "(none)"
renderList values = T.intercalate ", " values

lookupIndexBy :: (a -> Bool) -> [a] -> Maybe Int
lookupIndexBy predicate = go 0
  where
    go _ [] = Nothing
    go indexValue (entry : rest)
        | predicate entry = Just indexValue
        | otherwise = go (indexValue + 1) rest

drawHelp :: Widget Name
drawHelp =
    borderWithLabel (withAttr headingAttr (txt "Help")) $
        padAll 1 $
            vBox
                [ txt "Tab: cycle panes"
                , txt "j/k or arrows: move selection"
                , txt "/: search entities"
                , txt "t: cycle type filter"
                , txt "n: toggle neighborhood relationships"
                , txt "c: cycle comparison timeline"
                , txt "b: save current entity bookmark"
                , txt "1-9: jump to bookmark"
                , txt "u/y: undo or redo"
                , txt "?: toggle this help"
                , txt "q: quit"
                ]

safeIndex :: Int -> [a] -> Maybe a
safeIndex indexValue values
    | indexValue < 0 = Nothing
    | otherwise =
        case drop indexValue values of
            [] -> Nothing
            value : _ -> Just value

lookupIndex :: Eq a => a -> [a] -> Maybe Int
lookupIndex value = go 0
  where
    go _ [] = Nothing
    go currentIndex (entry : rest)
        | entry == value = Just currentIndex
        | otherwise = go (currentIndex + 1) rest

selectedAttr :: AttrName
selectedAttr = attrName "selected"

headingAttr :: AttrName
headingAttr = attrName "heading"

statusAttr :: AttrName
statusAttr = attrName "status"

mutedAttr :: AttrName
mutedAttr = attrName "muted"

attrMapDefinition :: AttrMap
attrMapDefinition =
    attrMap
        V.defAttr
        [ (selectedAttr, V.black `on` V.yellow)
        , (headingAttr, fg V.cyan)
        , (statusAttr, fg V.green)
        , (mutedAttr, fg V.brightBlack)
        ]
