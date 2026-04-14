package tui

type Rect struct {
	X      int
	Y      int
	Width  int
	Height int
}

type Regions struct {
	TopBar    Rect
	Chat      Rect
	Input     Rect
	StatusBar Rect
	Modal     Rect
}

func ComputeRegions(width, height, inputRows int) Regions {
	width = maxInt(0, width)
	height = maxInt(0, height)
	inputRows = clampInt(inputRows, 3, 10)

	topRows := boolRow(height >= 1)
	statusRows := boolRow(height >= 2)
	available := maxInt(0, height-topRows-statusRows)
	if inputRows > available {
		inputRows = available
	}
	chatRows := maxInt(0, available-inputRows)
	modalHeight := clampInt((height*40)/100, 3, maxInt(3, height))
	if modalHeight > height {
		modalHeight = height
	}
	modalWidth := clampInt((width*70)/100, minInt(width, 24), width)

	return Regions{
		TopBar:    Rect{X: 0, Y: 0, Width: width, Height: topRows},
		Chat:      Rect{X: 0, Y: topRows, Width: width, Height: chatRows},
		Input:     Rect{X: 0, Y: topRows + chatRows, Width: width, Height: inputRows},
		StatusBar: Rect{X: 0, Y: topRows + chatRows + inputRows, Width: width, Height: statusRows},
		Modal: Rect{
			X:      maxInt(0, (width-modalWidth)/2),
			Y:      maxInt(0, (height-modalHeight)/2),
			Width:  modalWidth,
			Height: modalHeight,
		},
	}
}

func boolRow(ok bool) int {
	if ok {
		return 1
	}
	return 0
}

func clampInt(v, lo, hi int) int {
	if hi < lo {
		hi = lo
	}
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
