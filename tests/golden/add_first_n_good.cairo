# @pre [ap + 2] > 0
# @post [ap - 3] == ([ap - 2] * ([ap - 2] + 1)) / 2
func main():
    [ap] = 0; ap++  # sum
    [ap] = 1; ap++  # i
    [ap] = 5; ap++  # n

    # @invariant [ap] == ([ap - 2] * ([ap - 2] + 1)) / 2
    loop:
    [ap] = [ap - 3] + [ap - 2]; ap++  # sum += i
    [ap] = [ap - 3] + 1; ap++  # ++i
    [ap] = [ap - 3] - 1; ap++  # --n
    jmp loop if [ap - 1] != 0  # goto loop if n != 0
    ret
end
