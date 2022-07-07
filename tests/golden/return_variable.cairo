struct Test:
    member x: felt
    member y: felt 
end 

# @post Return.res == 10
func test() -> (res: felt):
    return (res=10)
end

# @post Return.test.y == 10
func complex_return() -> (test: Test):
    return (test=Test(x=10, y=10))
end

# @post Return.test.y == 20 && Return.b == 30
func more_complex_return() -> (a: felt, test: Test, b: felt):
    return (a=10, test=Test(x=10,y=20), b=30)
end 

func main():
    test()
    ret
end