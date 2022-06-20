# @pre 1 == 1
# @post 13 == 13
func main():
    [ap] = 1; ap++
    [ap] = 2; ap++
    [ap] = [[ap - 2] + 7]; ap++
    [ap - 1] = [[ap - 3] + 7]
    [ap - 1] = [[ap - 2] + 8]
    ret
end
