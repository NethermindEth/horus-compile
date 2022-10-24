from starkware.cairo.lang.compiler.scoped_name import ScopedName

allowed_syscalls = [
    ScopedName.from_string("starkware.starknet.common.syscalls.get_caller_address"),
    ScopedName.from_string("starkware.starknet.common.syscalls.get_contract_address"),
    ScopedName.from_string("starkware.starknet.common.syscalls.get_block_timestamp"),
]
