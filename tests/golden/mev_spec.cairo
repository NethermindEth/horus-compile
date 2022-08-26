# @post [ap - 1] == 2 * 123456789987654321
func main():
    [ap] = 123456789987654321; ap++  # n
    [ap] = 0; ap++

    # @invariant [ap - 1] == 2 * (123456789987654321 - [ap - 2])
    loop:
    [ap] = [ap - 2] - 1; ap++
    [ap] = [ap - 2] + 2; ap++
    jmp loop if [ap - 2] != 0
    ret
end
