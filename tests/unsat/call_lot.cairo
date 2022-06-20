func a():
    [ap] = 0; ap++
    [ap] = 42; ap++
    ret
end

func b():
    [ap] = 1; ap++
    ret
end

func c():
    [ap] = 2; ap++
    ret
end

func d():
    [ap] = 3; ap++
    [ap] = 4; ap++
    ret
end

func e():
    [ap] = 4; ap++
    ret
end

func f():
    [ap] = 5; ap++
    ret
end

func main():
    [ap] = 42; ap++
    call a
    [ap] = 43; ap++
    call b
    [ap] = 44; ap++
    call c
    [ap] = 45; ap++
    call d
    [ap] = 46; ap++
    call e
    [ap] = 47; ap++
    call f
    [ap] = 48; ap++
    [ap] = 49; ap++
    [ap] = 50; ap++
    [ap - 1] = 0
    return ()
end