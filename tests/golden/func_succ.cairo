// @post [ap - 1] == 6
func main() {
    [ap] = 5, ap++;
    call succ;
    ret;
}

// @post [ap - 1] == [fp - 3] + 1
func succ(x) -> (res: felt) {
    [ap] = [fp - 3], ap++;
    [ap] = [ap - 1] + 1, ap++;
    ret;
}
