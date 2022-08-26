# @post [ap - 2] == [fp - 3] + [fp - 4]
func main():
    [ap] = [fp - 3]; ap++  # n
    [ap] = [fp - 4]; ap++  # m

    # @invariant [ap - 1] + [ap - 2] == [fp - 3] + [fp - 4]
    loop:
    [ap] = [ap - 2] + 1; ap++
    [ap] = [ap - 2] - 1; ap++
    jmp loop if [ap - 1] != 0
    ret
end
