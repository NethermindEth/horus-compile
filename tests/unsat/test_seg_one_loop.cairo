#pre 
func main():
    [ap] = 1; ap++
    [ap - 1] = 2; ap++
    [ap - 1] = 3; ap++
    [ap - 1] = 4; ap++
    #inv8
    loop:
    [ap - 1] = 5; ap++
    [ap - 1] = 6; ap++
    jmp loop
    [ap - 1] = 7
    ret
#post
end