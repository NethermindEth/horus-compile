func main():
    [ap] = 5; ap++
    [ap] = [ap - 1]; ap++
    l1:
    [ap] = [ap - 2] - 1; ap++
    [ap] = [ap - 1] + [ap - 2]; ap++
    jmp l1 if [ap - 2] != 0
    ret
end