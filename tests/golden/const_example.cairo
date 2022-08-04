%lang starknet
from starkware.cairo.common.math import assert_le, assert_lt, assert_nn_le, unsigned_div_rem
const BALANCE_UPPER_BOUND = 2 ** 64

# @post $Return.new_balance == balance + amount
# @post $Return.new_balance >= 0 && $Return.new_balance < BALANCE_UPPER_BOUND
func modify_account_balance{range_check_ptr}(
    balance : felt, amount : felt
) -> (new_balance) :
    tempvar res = balance + amount
    assert_nn_le(res, BALANCE_UPPER_BOUND - 1)
    return (new_balance = res)
end