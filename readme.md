<div align="center">
<br />
    <img src="./static/nethermind.png" alt="Ethereum" width="80" >

<br />
  <h2 align="center">Horus-Compile</h2>
  <p align="center">
    Cairo compiler plugin extending language with annotations
    <br />
    ·
    <a href="https://github.com/NethermindEth/horus-compile/issues">Report Bug</a>
    ·
    <a href="https://github.com/NethermindEth/horus-compile/issues">Request Feature</a>
  </p>
</div>

<br>

# Getting Started

You can use `poetry install` to install the required dependencies into your virtual environment.

<br>

Thereafter, you can utilise `horus-compile` to compile your specified Cairo code which may include the additional annotation standard (specify `--output` flag followed by JSON destination to specify where to save the generated ABI):

```bash
horus-compile <path_to_cairo_file> --output  <path_to_json_file_to_create>
```
