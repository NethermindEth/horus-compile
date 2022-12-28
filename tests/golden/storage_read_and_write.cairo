%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func balance(t: felt) -> (res: felt) {
}

// @post $Return.res == 1337
// @storage_update balance(t=10) := balance(t=10) + 1
func main{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}() -> (res: felt) {
    // balance.write(42);
    // let (blnc) = balance.read();
    let x = 1337;
    return (res=x);
}
