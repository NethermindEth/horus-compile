# @pre True
# @post [ap - 1] == 32
func main():
    [ap] = 5; ap++
    [ap] = 6; ap++
    call prod
    [ap] = [ap - 1] + 2; ap++
    ret
end
# @pre True
# @post [ap - 1] == [fp - 3] * [fp - 4]
func prod(x, y):
  [ap] = [fp - 3]; ap++ # n
  [ap] = [fp - 4]; ap++ # m
  [ap] = 0; ap++
  # @invariant [ap - 1] + [fp] * [ap-2] == [fp] * [fp + 1]
  loop:
    [ap] = [ap - 2] - 1; ap++	
    [ap] = [ap - 2] + [fp]; ap++
    jmp loop if [ap - 2] != 0                     
  ret                                             
end