// @post [ap - 1] == 26
func main() {
    [ap] = 5, ap++;
    call square_succ;
    ret;
}

// @post [ap - 1] == [fp - 3] + 1
func succ(x) -> (res: felt) {
    [ap] = [fp - 3], ap++;
    [ap] = [ap - 1] + 1, ap++;
    ret;
}

// @post [ap - 1] == [fp - 3] * [fp - 3] + 1
func square_succ(x) -> (res: felt) {
    [ap] = [fp - 3], ap++;
    [ap] = [ap - 1] * [ap - 1], ap++;
    call succ;
    ret;
}
