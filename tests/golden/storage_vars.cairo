%lang starknet
from starkware.cairo.common.math import assert_nn
from starkware.cairo.common.cairo_builtins import HashBuiltin
from starkware.starknet.common.syscalls import get_caller_address

struct Test:
    member x : felt
    member y : felt
end

@storage_var
func balance(user : felt) -> (res : felt):
end

@storage_var
func double_arg(a : felt, b : felt) -> (res : felt):
end

# @pre balance(10) == 20
# @pre balance(user=20) != 11
# @pre double_arg(a=x+10, b=[x]+20) == [x] * 100
# @post [double_arg(a=60, b=[[x]] + x)] == 10
# @storage_update balance(user=10):=balance(user=10)
# @storage_update balance(user=11):=12
# @storage_update balance(15):=18
@external
func test(x : felt):
    ret
end
