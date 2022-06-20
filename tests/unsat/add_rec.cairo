func add(m, n) -> (res):
    if m == 0:
        return (res=n)
    end
    let (next) = add(m - 1, n)
    return (res=1 + next)
end

func main():
    let (res) = add(2, 2)
    assert res = 5
    ret
end