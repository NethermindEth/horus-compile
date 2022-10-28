<div align="center">
<br />
    <img src="./static/nethermind.png" alt="Ethereum" width="80" >

<br />
  <h2 align="center">Horus</h2>
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

# Introduction

Horus is a formal verification tool based on SMT checkers which allows users to annotate their StarkNet contracts with assertions and therafter verify that they hold by discharging them to an SMT solver (or multiple ones).

<br>

# Pre-requisites

In order to utilise Horus you will require several software dependencies such as:

- Python 3.7x
- Stack (Haskell build tool)
- Poetry (Python package and depedency manager)

In addition to the above, you will need to ensure that you have the following SMT solvers installed on your machine:

- z3 (version 4.10.2)
- mathsat (version 5.6.8)

> Note: If your machine has x86 or x64 architecture you can install these solvers by running the install scripts located in `horus-check/scripts/ci/*` else you will have to figure out the native solution to installing it on your machine (e.g. arm64 architecture on M1/M2 Macbooks).

<br>

# Setting up `horus-compile`

Firstly, clone the `horus-compile` and `horus-checker` repositories to your machine.

<br>

The next step involved is setting up `horus-compile` to be used across all the Horus repositories. This requires setting up a Python virtual environment and installing the compiler dependencies, thereafter you should be able to access the `horus-compile` commandline utility from anywhere on your machine (specifically we will want to make use of this once we want to start running compiled code through the SMT checkers for formal verification assertions).

<br>

To get started with `horus-compile` setup, create a virtual environment and activate it:

```bash
# create virtual environment <venv-name>
python -m venv ~/path/to/env-dir/<venv-name>
# use virtual environment
source ~/path/to/env-dir/<venv-name>/bin/activate
```

<br>

While being at the root directory of the `horus-compile` , make sure you are in the virtual environment and install the Python dependencies using `poetry`:

```bash
poetry install
```

You can use `poetry install` to install the required dependencies into your virtual environment.

<br>

At this point, the `horus-compile` command-line utility should be ready for use, to compile annotated Cairo code into files that the `horus-checker` will be able to use later.

You can utilise `horus-compile` to compile your specified Cairo code which may include the additional annotation standard (specify `--output` flag followed by JSON destination to specify where to save the generated ABI):

```bash
horus-compile <path_to_cairo_file> --output  <path_to_json_file_to_create>
```

<br>

# Setting up `horus-checker`

Go to the `horus-checker` directory and make sure you are in the virtual environment with which you installed the dependencies for `horus-compile`. You can quickly check if horus-compile can be called from this directory by calling the same command from above pointing at an specific Cairo file you wish to comiple:

```bash
horus-compile <path_to_cairo_file> --output  <path_to_json_file_to_create>
```

<br>

If the above worked, you can proceed now with setting up `horus-checker` and installing required Haskell dependencies (you should have `stack` installed for Haskell use). Install the dependencies with the following command:

```bash
stack build
```

<br>

If the above command was executed without error, then you are finished with the initial setup and are now ready to work with Horus

<br>

# Using `horus-check`

In the `horus-checker` directory, you should now be able to use the Horus checker after installing the Haskell dependencies using `stack`.

In order to use the Horus checker you would need to have used `horus-compile` to generate a JSON file including the compiled code and other attributes required by the checker.

<br>

Thereafter you can point to the specific JSON file that you would like to run the Horus checker over, you will also need to use the `-s` flag to specify which SMT solvers you would like to use for the testing:

<br>

```
stack exec horus-check -- ./<path-to-file>/example.json -s z3
```

<br>

> You can also call the Horus checker with multiple SMT solvers, below you can see the same example but with all the solver options added after the `-s` flag:

```bash
stack exec horus-check -- ./<path-to-file>/example.json -s z3 mathsat cvc5
```
