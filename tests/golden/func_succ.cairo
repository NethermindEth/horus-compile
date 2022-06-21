# @post [ap - 1] == 6
func main():
    [ap] = 5; ap++
    call succ
    ret
end

# @post [ap - 1] == [fp - 3] + 1
func succ(x) -> (res):
    [ap] = [fp - 3]; ap++
    [ap] = [ap - 1] + 1; ap++
    ret
end