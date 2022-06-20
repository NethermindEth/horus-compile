# @pre 1 == 1
# @post 13 == 13
func main():
    [ap] = 1; ap++
    call main
    ret
end
# @pre 2 == 2
# @post 14 == 14
func f():
    [ap] = 1; ap++
    call g
    ret
end
# @pre 3 == 3
# @post 15 == 15
func g():
    [ap] = 1; ap++
    call f
    ret
end