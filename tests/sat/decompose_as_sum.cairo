func main():
    [ap] = 10; ap++
    %{
        memory[ap] = 6
        memory[ap + 1] = 4 
    %}
    [ap - 1] = [ap] + [ap + 1]

    ret
end
