func main():
    [ap] = 0; ap++
    [ap] = 2; ap++
    [ap] = 1; ap++
    [ap - 1] = [ap] * [ap + 1]
    [fp] = [fp + 1] * [ap]
    ret
end