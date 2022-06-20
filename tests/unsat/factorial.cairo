func factorial(n) -> (fact):
    if n == 0:
        return (fact=1)
    end
    let (next) = factorial(n - 1)
    return (fact=n * next)
end

func main():
    let (res) = factorial(3)
    assert res = 5
    ret
end