# @post [ap - 1] == 0
func main():
  [ap] = 123456789987654321; ap++ # n                         
  # @invariant 0 < [ap - 1] && [ap - 1] <= 123456789987654321
  loop:                                           
    [ap] = [ap - 1] - 1; ap++                     
    jmp loop if [ap - 1] != 0                     
  ret                                             
end