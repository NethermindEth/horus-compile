#pre
func main():
    [ap] = 0; ap++
    loop: #INV2
    [ap] = [ap - 1] * 2; ap++
    jmp loop if [ap-2] != 0
    #some_label - True
    [ap] = 42; ap++
    [ap] = 42; ap++
    [ap] = 42; ap++
    [ap] = 42; ap++
    ret
end
#post