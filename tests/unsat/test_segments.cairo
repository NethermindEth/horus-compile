func faw():
    [ap] = 5; ap++
    loop:
    [ap] = [ap - 1] - 1; ap++
    jmp loop if [ap - 1] != 0
    [ap - 1] = 0
    ret
end

func main():
    [ap] = 0; ap++
    [ap] = 2; ap++
    call faw
    [ap] = 3; ap++
    return ()
end