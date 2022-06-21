struct Point:
    member x: felt
    member y: felt
end

struct NestedStruct:
    member point: Point
    member z: felt
end

# @declare $n : NestedStruct
# @declare $m : (felt, Point)
func main():
    tempvar a: NestedStruct = NestedStruct(point=Point(x=10, y=20), z=30)
    # @require $n == a
    tempvar b: (felt, Point) = (10, Point(x=20, y=30))
    # @require $m == b
    ret
end