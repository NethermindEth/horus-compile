# @pre 1 == 1
# @post [ap] == 13
func main():
    [ap] = 1; ap++
    [ap] = 2; ap++
    # @invariant 2 == 2
    loop:
    [ap] = 3; ap++
    [ap] = 4; ap++
    [ap] = 5; ap++
    [ap] = 0; ap++
    jmp fin if [ap - 1] != 0
    [ap] = 7; ap++
    [ap] = 8; ap++
    [ap] = 0; ap++
    jmp loop if [ap - 1] != 0
    [ap] = 10; ap++
    [ap] = 11; ap++
    call f
    [ap] = 12; ap++
    # @invariant 42 == 42
    fin:
    [ap] = 13
    ret
end
# @pre 33 == 33
# @post 77 == 77
func f():
    [ap] = 1; ap++
    [ap] = 2; ap++
    # @invariant 22 == 22
    woop:
    [ap] = 3; ap++
    [ap] = 4; ap++
    [ap] = 5; ap++
    call f
    [ap] = 0; ap++
    jmp win if [ap - 1] != 0
    [ap] = 7; ap++
    [ap] = 8; ap++
    [ap] = 0; ap++
    jmp woop if [ap - 1] != 0
    [ap] = 10; ap++
    [ap] = 11; ap++
    [ap] = 12; ap++
    # @invariant 44 == 44
    win:
    [ap] = 13
    ret
end