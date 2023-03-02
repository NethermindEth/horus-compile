%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func stack(i: felt) -> (value: felt) {
}

@storage_var
func stack_ptr() -> (i: felt) {
}

// @pre stack_ptr().i >= 2
// @storage_update stack(i=stack_ptr().i - 1).value := stack(stack_ptr().i - 2).value + stack(stack_ptr().i - 1).value
// @storage_update stack_ptr().i := stack_ptr().i - 1
func stack_add{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}() {
    let (ptr) = stack_ptr.read();
    let (x) = stack.read(ptr - 2);
    let (y) = stack.read(ptr - 1);
    stack.write(ptr - 2, x + y);
    stack_ptr.write(ptr - 1);
    return ();
}

// @storage_update stack(i=stack_ptr().i - 1).value := v
// @storage_update stack_ptr().i := stack_ptr().i + 1
func stack_lit{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}(v: felt) {
    let (ptr) = stack_ptr.read();
    stack.write(ptr, v);
    stack_ptr.write(ptr + 1);
    return ();
}

// @pre stack_ptr().i >= 1
// @post $Return.res == stack(stack_ptr().i - 1).value
func stack_top{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}() -> (res: felt) {
    let (ptr) = stack_ptr.read();
    let (res) = stack.read(ptr - 1);
    return (res,);
}

// @post $Return.res == 11
// @storage_update stack(i=stack_ptr().i - 1).value := 11
// @storage_update stack_ptr().i := stack_ptr().i + 1
func main{syscall_ptr: felt*, pedersen_ptr: HashBuiltin*, range_check_ptr}() -> (res: felt) {
    stack_lit(5);
    stack_lit(6);
    stack_add();
    let (top) = stack_top();
    return (top,);
}
