{-# LANGUAGE OverloadedStrings #-}

module Seuss.Render.SVG
    ( SvgOptions(..)
    , defaultSvgOptions
    , renderSvg
    ) where

import Data.Text (Text)
import qualified Data.Text as T
import Seuss.Config.Loader (SvgTheme(..), darkTheme)
import Seuss.Render.Layout

data SvgOptions = SvgOptions
    { svgWidth :: Int
    , svgHeight :: Int
    , svgTitle :: Text
    , svgTheme :: SvgTheme
    }
    deriving (Eq, Show)

defaultSvgOptions :: SvgOptions
defaultSvgOptions =
    SvgOptions
        { svgWidth = 1600
        , svgHeight = 900
        , svgTitle = "Seuss"
        , svgTheme = darkTheme
        }

renderSvg :: SvgOptions -> Layout -> Text
renderSvg options layout =
    T.unlines $
        [ "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        , "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" <> showText (svgWidth options) <> "\" height=\"" <> showText (svgHeight options) <> "\" viewBox=\"0 0 " <> showText (svgWidth options) <> " " <> showText (svgHeight options) <> "\">"
        , "<rect width=\"100%\" height=\"100%\" fill=\"" <> themeBackground (svgTheme options) <> "\"/>"
        , "<text x=\"32\" y=\"48\" fill=\"" <> themeText (svgTheme options) <> "\" font-size=\"28\" font-family=\"monospace\">" <> escapeXml (svgTitle options) <> "</text>"
        ]
            ++ map renderTimeline (layoutTimelines layout)
            ++ map renderEntity (layoutEntities layout)
            ++ map renderRelationship (layoutRelationships layout)
            ++ ["</svg>"]
  where
    minTime = layoutMinTime layout
    maxTime = max (layoutMaxTime layout) (minTime + 1)
    drawableWidth = fromIntegral (svgWidth options - 120) :: Double
    originX = 80.0 :: Double
    originY = 100.0 :: Double
    laneHeight = 54.0 :: Double
    scaleX ordinal =
        let numerator = fromIntegral (ordinal - minTime)
            denominator = fromIntegral (maxTime - minTime)
         in originX + numerator / denominator * drawableWidth
    laneY laneIndex = originY + fromIntegral laneIndex * laneHeight
    renderTimeline timeline =
        T.concat
            [ "<g>"
            , "<line x1=\""
            , showDouble (scaleX (layoutTimelineStart timeline))
            , "\" y1=\""
            , showDouble (laneY (layoutTimelineLane timeline))
            , "\" x2=\""
            , showDouble (scaleX (layoutTimelineEnd timeline))
            , "\" y2=\""
            , showDouble (laneY (layoutTimelineLane timeline))
            , "\" stroke=\""
            , themeText (svgTheme options)
            , "\" stroke-width=\"3\" opacity=\"0.35\"/>"
            , "<text x=\"20\" y=\""
            , showDouble (laneY (layoutTimelineLane timeline) + 6)
            , "\" fill=\""
            , themeTimeline (svgTheme options)
            , "\" font-family=\"monospace\" font-size=\"16\">"
            , escapeXml (layoutTimelineName timeline)
            , "</text>"
            , "</g>"
            ]
    renderEntity entity =
        let y = laneY (layoutEntityLane entity) - 16
            x = scaleX (layoutEntityStart entity)
            width = max 14.0 (scaleX (layoutEntityEnd entity) - x)
         in T.concat
                [ "<g>"
                , "<rect x=\""
                , showDouble x
                , "\" y=\""
                , showDouble y
                , "\" width=\""
                , showDouble width
                , "\" height=\"28\" rx=\"6\" fill=\""
                , themeEntity (svgTheme options)
                , "\" opacity=\"0.85\"/>"
                , "<text x=\""
                , showDouble (x + 8)
                , "\" y=\""
                , showDouble (y + 19)
                , "\" fill=\""
                , themeText (svgTheme options)
                , "\" font-family=\"monospace\" font-size=\"14\">"
                , escapeXml (layoutEntityName entity <> " [" <> layoutEntityType entity <> "]")
                , "</text>"
                , "</g>"
                ]
    renderRelationship relationship =
        case lookupEntityMidpoint (layoutRelSource relationship) of
            Nothing -> ""
            Just (sourceX, sourceY) ->
                case lookupEntityMidpoint (layoutRelTarget relationship) of
                    Nothing -> ""
                    Just (targetX, targetY) ->
                        T.concat
                            [ "<g>"
                            , "<line x1=\""
                            , showDouble sourceX
                            , "\" y1=\""
                            , showDouble sourceY
                            , "\" x2=\""
                            , showDouble targetX
                            , "\" y2=\""
                            , showDouble targetY
                            , "\" stroke=\""
                            , themeRelationship (svgTheme options)
                            , "\" stroke-width=\"1.5\" stroke-dasharray=\"5,5\"/>"
                            , "<text x=\""
                            , showDouble ((sourceX + targetX) / 2)
                            , "\" y=\""
                            , showDouble ((sourceY + targetY) / 2 - 4)
                            , "\" fill=\""
                            , themeRelationship (svgTheme options)
                            , "\" font-family=\"monospace\" font-size=\"12\">"
                            , escapeXml (maybe "rel" id (layoutRelLabel relationship))
                            , "</text>"
                            , "</g>"
                            ]
    lookupEntityMidpoint name =
        case filter (\entity -> layoutEntityName entity == name) (layoutEntities layout) of
            [] -> Nothing
            (entity : _) ->
                let x1 = scaleX (layoutEntityStart entity)
                    x2 = scaleX (layoutEntityEnd entity)
                 in Just ((x1 + x2) / 2, laneY (layoutEntityLane entity) - 2)

showText :: Show a => a -> Text
showText = T.pack . show

showDouble :: Double -> Text
showDouble = T.pack . show

escapeXml :: Text -> Text
escapeXml =
    T.concatMap
        ( \c ->
            case c of
                '<' -> "&lt;"
                '>' -> "&gt;"
                '&' -> "&amp;"
                '"' -> "&quot;"
                '\'' -> "&apos;"
                _ -> T.singleton c
        )
