# @pre True
# @post [ap - 1] == 0
func main():
  [ap] = 5; ap++ # n                           
  # @invariant 0 < [ap - 1] /\ [ap - 1] <= 5    
  loop:                                         
    [ap] = [ap - 1] - 1; ap++                   
    jmp end_loop if [ap - 1] == 0
    jmp loop
  # @invariant [ap - 1] == 0
  end_loop:
    ret                                           
end
