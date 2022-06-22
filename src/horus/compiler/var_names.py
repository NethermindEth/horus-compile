import z3

AP_VAR_NAME = "ap"
PC_VAR_NAME = "pc"
FP_VAR_NAME = "fp"
MEMORY_MAP_NAME = "memory"
MEMORY_BOUND_VAR_NAME = "memory_bound"
PRIME_CONST_NAME = "prime"
IDENT_UF_NAME = "MEM"

ap, fp, pc, prime = z3.Ints(
    f"{AP_VAR_NAME} {FP_VAR_NAME} {PC_VAR_NAME} {PRIME_CONST_NAME}"
)
memory = z3.Function(MEMORY_MAP_NAME, z3.IntSort(), z3.IntSort())

HORUS_DECLS = {
    AP_VAR_NAME: ap,
    FP_VAR_NAME: fp,
    PC_VAR_NAME: pc,
    PRIME_CONST_NAME: prime,
    MEMORY_MAP_NAME: memory,
}
