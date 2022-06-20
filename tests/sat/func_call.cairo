func f():
    [ap] = 12; ap++
    ret
end

func main():
    [ap] = 1; ap++
    test:
    call f
    jmp test
end  