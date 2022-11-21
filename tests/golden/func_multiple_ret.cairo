// @post (([ap - 1] == [fp - 3] + 1) and ([fp - 3] == 0)) or (([ap - 1] == [fp - 3] - 1) and ([fp - 3] > 0))
func succpred(m) {
    jmp add if [fp - 3] != 0;
    [ap] = [fp - 3] + 1, ap++;
    ret;

    // @invariant [fp - 3] > 0
    add:
    [ap] = [fp - 3] - 1, ap++;
    ret;
}

// @post [ap - 1] == 41
func main() {
    [ap] = 42, ap++;
    call succpred;
    ret;
}
