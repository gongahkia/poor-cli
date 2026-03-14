{-# LANGUAGE OverloadedStrings #-}

module Seuss.TUI.App
    ( runSeussTui
    ) where

import Brick
import qualified Brick.Main as M
import Brick.Util (fg, on)
import qualified Graphics.Vty as V
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
    [ vBox
        [ borderWithLabel (withAttr headingAttr (txt "Seuss Haskell TUI")) $
            hBox
                [ hLimit 32 (drawPane "Timelines" (appPane state == PaneTimelines) timelineRows)
                , hLimit 48 (drawPane "Entities" (appPane state == PaneEntities) entityRows)
                , hLimit 36 (drawPane "Relationships" (appPane state == PaneRelationships) relationshipRows)
                , drawPane "Inspector" (appPane state == PaneDiagnostics) inspectorRows
                ]
        , drawStatus state
        ]
    ]
  where
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
    diagnosticDetails =
        case safeIndex (appDiagnosticIndex state) (appDiagnostics state) of
            Nothing -> ["Diagnostics", "  none"]
            Just diagnostic ->
                [ "Diagnostic"
                , "  " <> renderDiagnostic diagnostic
                ]

handleEvent :: AppState -> BrickEvent Name e -> EventM Name (Next AppState)
handleEvent state (VtyEvent eventValue) =
    case eventValue of
        V.EvKey (V.KChar 'q') [] -> M.halt state
        V.EvKey (V.KChar '\t') [] -> M.continue (advancePane state)
        V.EvKey V.KUp [] -> M.continue (moveSelection (-1) state)
        V.EvKey (V.KChar 'k') [] -> M.continue (moveSelection (-1) state)
        V.EvKey V.KDown [] -> M.continue (moveSelection 1 state)
        V.EvKey (V.KChar 'j') [] -> M.continue (moveSelection 1 state)
        V.EvKey (V.KChar '/') [] ->
            M.continue state{appMode = ModeSearch, appStatus = "Search mode"}
        V.EvKey (V.KChar 't') [] -> M.continue (cycleTypeFilter state)
        V.EvKey (V.KChar 'n') [] -> M.continue (toggleNeighborhood state)
        V.EvKey V.KEsc [] -> M.continue (exitSearch state)
        V.EvKey V.KBS [] -> M.continue (searchBackspace state)
        V.EvKey V.KEnter [] -> M.continue (exitSearch state)
        V.EvKey (V.KChar charValue) [] -> M.continue (searchAppend charValue state)
        _ -> M.continue state
handleEvent state _ = M.continue state

advancePane :: AppState -> AppState
advancePane state =
    state
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
    case appPane state of
        PaneTimelines ->
            state
                { appTimelineIndex =
                    boundedMove delta (appTimelineIndex state) (layoutTimelines (appLayout state))
                }
        PaneEntities ->
            state
                { appEntityIndex =
                    boundedMove delta (appEntityIndex state) (visibleEntities state)
                }
        PaneRelationships ->
            state
                { appRelationshipIndex =
                    boundedMove delta (appRelationshipIndex state) (visibleRelationships state)
                }
        PaneDiagnostics ->
            state
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
     in state
            { appTypeFilter = nextFilter
            , appEntityIndex = 0
            , appStatus = "Cycled type filter"
            }

toggleNeighborhood :: AppState -> AppState
toggleNeighborhood state =
    state
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
            state
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
            state
                { appSearch = appSearch state <> T.singleton charValue
                , appEntityIndex = 0
                , appStatus = "Filtering entities"
                }

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
