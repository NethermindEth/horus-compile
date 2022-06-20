# @pre fp == ap
# @post [ap - 1] == 5
func main():
    [ap] = 5; ap++
    call comp_id
    ret
end
# @pre fp == ap
# @post [ap - 1] == [fp - 3] + 1
func range_check(x) -> (res):
    [ap] = [fp - 3]; ap++
    [ap] = [ap - 1] + 1; ap++
    ret
end