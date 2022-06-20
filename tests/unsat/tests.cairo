# @pre 1 == 1
# @post 13 == 13
func main():
    [ap] = 1; ap++
    [ap] = 2; ap++
    [ap] = [[ap - 2]]; ap++
    [ap - 1] = [[ap - 3]]
    [ap - 1] = [[ap - 2] + 1] # change to [ap - 1] = [[ap - 2] - 1] if you want SAT
    ret
end