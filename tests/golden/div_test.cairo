%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func test1() -> (res: felt) {
}

@storage_var
func test2() -> (res: felt) {
}

// @post x / y == 10
// @storage_update test2() := test1() / x
func main{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}(x: felt, y: felt) {
    let (z) = test1.read();
    test2.write(z / x);
    // @assert x / y == 10
    ret;
}
