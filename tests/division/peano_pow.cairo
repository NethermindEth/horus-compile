# @post [ap - 2] == 2 ** [fp + 1] 
func main():
  [ap] = 1; ap++ # 2 ** (10-i)
  [ap] = 10; ap++ #i
  # @invariant [ap - 2] == 2 ** ([fp + 1] - [ap - 1])
  loop:
    [ap] = [ap - 2] * 2; ap++	
    [ap] = [ap - 2] - 1; ap++
    jmp loop if [ap - 1] != 0                     
  ret                                             
end