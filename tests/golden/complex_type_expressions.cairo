struct Point:
    member x : felt
    member y : felt
end

struct NestedStruct:
    member point : Point
    member z : felt
end

# @declare $n : NestedStruct
# @declare $m : (felt, Point)
# @post $n == $Return.a
# @post $m == $Return.b
func _main() -> (a : NestedStruct, b : (felt, Point)):
    tempvar a : NestedStruct = NestedStruct(point=Point(x=10, y=20), z=30)
    tempvar b : (felt, Point) = (10, Point(x=20, y=30))
    return (a=a, b=b)
end
