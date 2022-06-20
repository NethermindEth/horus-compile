func sum(n) -> (res):
    if n == 0:
        return (res=0)
    end
    let (next) = sum(n - 1)
    return (res=n + next)
end

func main():
    let (res) = sum(3)
    assert res = 5
    ret
end