func add_base(n) -> (res):
    return (res=n)
end

func add_one(n) -> (res):
    let (next) = add_base (n)
    return (res=next + 1)
end

func add_two(n) -> (res):
    let (next) = add_one (n)
    return (res=next + 1)
end

func main():
    let (res) = add_two(2)
    assert res = 5
    ret
end