from starkware.cairo.common.cairo_builtins import HashBuiltin
from starkware.cairo.common.hash import hash2

struct Test:
    member x: felt
    member y: felt 
end 

# @post res == 10
func simple_ret() -> (res: felt):
    return (res=10)
end

# @post test.y == 10
func complex_return() -> (test: Test):
    return (test=Test(x=10, y=10))
end

# @post test.y == 20 && b == 30
func more_complex_return() -> (a: felt, test: Test, b: felt):
    return (a=10, test=Test(x=10,y=20), b=30)
end

# @post test.y == 20 && b == 30
func pointer_to_a_struct() -> (a: felt, test: Test*, b: felt):
    return (a=10, test=new Test(x=10,y=20), b=30)
end

# @post hash_ptr0 == hash_ptr0
func implicit_variable{hash_ptr0 : HashBuiltin*}() -> (x : felt):
    let (x) = hash2{hash_ptr=hash_ptr0}(10, 10)
    return (x=x)
end

func main():
    simple_ret()
    ret
end