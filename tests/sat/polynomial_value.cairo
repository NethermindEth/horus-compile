# the value of x^3+23x^2+45x+67, x=100
func main():
    [ap] = 100; ap++
    [ap] = [fp] + 23; ap++
    [ap] = [fp] * [ap - 1]; ap++
    [ap] = [ap - 1] + 45; ap++
    [ap] = [fp] * [ap - 1]; ap++
    [ap] = [ap - 1] + 67; ap++
    # @assert [fp] == 100
    # @assert [fp + 1] == 123
    # @assert [fp + 2] == 12300
    # @assert [fp + 3] == 12345
    # @assert [fp + 4] == 1234500
    # @assert [fp + 5] == 1234567

    ret
end