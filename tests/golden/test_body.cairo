# @pre [ap - 2] + [ap - 1] == [fp + 2] + 1 && [ap - 3] == ([ap - 2] * ([ap - 2] - 1)) / 2
# @post [ap - 3] == (([fp + 2] + 1) * [fp + 2]) / 2
func main():
    # @invariant [ap - 2] + [ap - 1] == [fp + 2] + 1 && [ap - 3] == ([ap - 2] * ([ap - 2] - 1)) / 2
    loop:
    [ap] = [ap - 3] + [ap - 2]; ap++  # sum += i
    [ap] = [ap - 3] + 1; ap++  # ++i
    [ap] = [ap - 3] - 1; ap++  # --n
    jmp loop if [ap - 1] != 0  # goto loop if n != 0
    ret
end
