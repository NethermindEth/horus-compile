%lang starknet
%builtins range_check

from starkware.cairo.common.math_cmp import is_le

# @post (a > b -> $Return.c == a) && (b > a -> $Return.c == b)
@external
@l1_handler
func max{range_check_ptr}(a, b) -> (c):
    let (le) = is_le(a, b)
    if le != 0:
        return (b)
    else:
        return (a)
    end
end
