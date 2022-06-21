# @declare $k : felt
func main():
    [ap] = 1; ap++
    # @require [ap - 1] == 1
    # @invariant $k == ap - fp /\ [ap - 1] == 2 ** ($k - 1)
    loop:
    [ap] = [ap - 1] * 2; ap++
    jmp loop
end