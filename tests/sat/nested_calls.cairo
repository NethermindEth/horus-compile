func f():
    [ap] = 11; ap++
    ret
end

func g():
    [ap] = 1337; ap++
    call f
    ret
end

func main():
    [ap] = 42; ap++
    call g
    ret
end
