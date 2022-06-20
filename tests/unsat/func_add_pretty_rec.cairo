# @pre True
# @post [ap - 1] == [fp - 3] + [fp - 4]
func add(m, n) -> (res):
    jmp next if m != 0
        return (n)
    # @invariant [fp - 4] > 0
    next: 
        let (added) = add(m - 1, n)
        return (added + 1)
end
# @pre True
# @post [ap - 1] == 5
func main():
    let (res) = add(2, 3)
    ret
end