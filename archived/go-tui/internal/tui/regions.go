package tui

type Rect struct {
	X      int
	Y      int
	Width  int
	Height int
}

type Regions struct {
	TopBar       Rect
	Chat         Rect
	Users        Rect
	Input        Rect
	TypingFooter Rect
	StatusBar    Rect
	Modal        Rect
}

func ComputeRegions(width, height, inputRows int, typingRowsOpt ...int) Regions {
	return ComputeRegionsWithUsers(width, height, inputRows, false, typingRowsOpt...)
}

func ComputeRegionsWithUsers(width, height, inputRows int, usersOpen bool, typingRowsOpt ...int) Regions {
	width = maxInt(0, width)
	height = maxInt(0, height)
	inputRows = clampInt(inputRows, 3, 10)
	typingRows := 0
	if len(typingRowsOpt) > 0 && typingRowsOpt[0] > 0 {
		typingRows = 1
	}

	topRows := boolRow(height >= 1)
	statusRows := boolRow(height >= 2)
	if height-topRows-statusRows < typingRows {
		typingRows = maxInt(0, height-topRows-statusRows)
	}
	available := maxInt(0, height-topRows-statusRows-typingRows)
	if inputRows > available {
		inputRows = available
	}
	chatRows := maxInt(0, available-inputRows)
	chatWidth := width
	users := Rect{}
	if usersOpen {
		chatWidth = maxInt(0, width-28-1)
		users = Rect{X: chatWidth + 1, Y: topRows, Width: minInt(28, width), Height: chatRows}
	}
	modalHeight := clampInt((height*75)/100, 3, maxInt(3, height))
	if modalHeight > height {
		modalHeight = height
	}
	modalWidth := clampInt((width*70)/100, minInt(width, 24), width)

	return Regions{
		TopBar:       Rect{X: 0, Y: 0, Width: width, Height: topRows},
		Chat:         Rect{X: 0, Y: topRows, Width: chatWidth, Height: chatRows},
		Users:        users,
		Input:        Rect{X: 0, Y: topRows + chatRows, Width: width, Height: inputRows},
		TypingFooter: Rect{X: 0, Y: topRows + chatRows + inputRows, Width: width, Height: typingRows},
		StatusBar:    Rect{X: 0, Y: topRows + chatRows + inputRows + typingRows, Width: width, Height: statusRows},
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
