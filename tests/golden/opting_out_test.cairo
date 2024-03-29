%lang starknet

struct Stack {
    value: felt,
    next: Stack*,
}

namespace _Stack {
    func empty() -> (stack: Stack*) {
        return (cast(0, Stack*),);
    }

    // @pre (cast(stack, felt) != 0) and (cast(stack.next, felt) != 0)
    // @post [ap - 2] == stack.value + stack.next.value and $Return.stack_ == stack.next.next
    func add(stack: Stack*) -> (stack_: Stack*) {
        let x = stack.value;
        let y = stack.next.value;
        return (new Stack(value=x + y, next=stack.next.next),);
    }

    // @post [ap - 2] == i and $Return.stack_.next == stack
    func lit(stack: Stack*, i: felt) -> (stack_: Stack*) {
        return (new Stack(value=i, next=stack),);
    }

    // @pre cast(stack, felt) != 0
    // @post $Return.res == stack.value
    func top(stack: Stack*) -> (res: felt) {
        return (stack.value,);
    }
}

// @post $Return.res == 11
func main_() -> (res: felt) {
    let (stack) = _Stack.empty();
    let (stack) = _Stack.lit(stack, 5);
    let (stack) = _Stack.lit(stack, 6);
    let (top) = _Stack.top(stack);
    return (top,);
}
