%builtins range_check

# @pre True
# @post [ap - 1] == 5
func main{range_check_ptr : felt*}():
    [ap] = 5; ap++
    call comp_id
    ret
end
# @pre True
# @post [fp - 4] >= 0 \/ [fp - 4] < 340282366920938463463374607431768211456))
func range_check{range_check_ptr : felt*}(x):
    [ap] = x; ap++
    [range_check_ptr] = [ap - 1]
    let range_check_ptr = range_check_ptr + 1
    ret
end