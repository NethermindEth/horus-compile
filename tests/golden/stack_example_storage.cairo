%lang starknet

from starkware.cairo.common.cairo_builtins import HashBuiltin

@storage_var
func stack(i: felt) -> (value: felt):
end

@storage_var
func stack_ptr() -> (i: felt):
end

# @pre stack_ptr() >= 2
# @state stack(i=stack_ptr() - 1) = stack(stack_ptr() - 2) + stack(stack_ptr() - 1)
# @state stack_ptr() = stack_ptr() - 1
func stack_add{syscall_ptr: felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}():
    let (ptr) = stack_ptr.read()
    let (x) = stack.read(ptr - 2)
    let (y) = stack.read(ptr - 1)
    stack.write(ptr - 2, x + y)
    stack_ptr.write(ptr - 1)
    return ()
end

# @state stack(i=stack_ptr() - 1) = v
# @state stack_ptr() = stack_ptr() + 1
func stack_lit{syscall_ptr: felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}(v : felt):
    let (ptr) = stack_ptr.read()
    stack.write(ptr, v)
    stack_ptr.write(ptr + 1)
    return ()
end

# @pre stack_ptr() >= 1
# @post $Return.res == stack(stack_ptr() - 1)
func stack_top{syscall_ptr: felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (res : felt):
    let (ptr) = stack_ptr.read()
    let (res) = stack.read(ptr - 1)
    return (res)
end


# @post $Return.res == 11
# @state stack(i=stack_ptr() - 1) = 11
# @state stack_ptr() = stack_ptr() + 1
func main{syscall_ptr: felt*, pedersen_ptr : HashBuiltin*, range_check_ptr}() -> (res : felt):
    stack_lit(5)
    stack_lit(6)
    stack_add()
    let (top) = stack_top()
    return (top)
end