# PRE
func main():
    [ap] = 42; ap++            # 0
    loop: # INV                # 2
    [ap] = 43; ap++            # 2
    jmp loop if [ap+2345] != 0 # 4
    [ap] = 44; ap++            # 6
    [ap] = 45; ap++            # 8
    ret
end
# POST