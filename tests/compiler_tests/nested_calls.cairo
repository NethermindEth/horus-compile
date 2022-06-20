# @pre [ap - 3] == 1337
# @post [ap - 1] == 11
func f():
    [ap] = 11; ap++
    ret
end

# @pre [ap - 3] == 42
# @post [ap - 1] == 11
# @post [ap - 4] == 1337
func g():
    [ap] = 1337; ap++
    call f
    ret
end

func main():
    [ap] = 42; ap++
    # @require [ap - 1] == 42
    call g
    ret
end
