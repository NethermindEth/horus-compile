func main():
    # @require True
    # @assert True
    [ap] = 1; ap++
    # @require 1 == 0
    [ap - 1] = [ap] * 55555555555; ap++ # @require 1 == 2
    # @require 1 == 3
    # @require True
    ret
    # @require False
end