// @pre True
// @post [ap - 1] == 42
func main() {
    [ap] = 42, ap++;
    call id;
    ret;
}

// @pre [fp - 3] > 42
// @post [ap - 1] == [fp - 3] + 1
func id(x) {
    [ap] = [fp - 3] + 1, ap++;
    ret;
}
