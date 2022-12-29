## Introduction

This is the compiler for the Horus formal verification tool. See the [main
repository](https://github.com/NethermindEth/horus-checker) for full
documentation.

## Installation

Make sure you have Python 3 installed, and run:

```console
pip install git+https://github.com/NethermindEth/horus-compile.git@master
```

## Usage

```console
horus-compile [-h] [--abi ABI] [--disable_hint_validation]
              [--account_contract] [--prime PRIME]
              [--cairo_path CAIRO_PATH] [--preprocess]
              [--output OUTPUT] [--no_debug_info]
              [--cairo_dependencies CAIRO_DEPENDENCIES]
              [--no_opt_unused_functions] [-v]
              file [file ...]
```
A tool to compile checked StarkNet contracts.

Emits a compiled Cairo program in the form of JSON, printed to `stdout` by default.

#### Positional arguments

`file`

One or more Cairo programs to compile.

#### Flags
`-h, --help`

Show a help message and exit

`--abi ABI`

Dump the contract's ABI (application binary interface)
to a file. This is a JSON list containing metadata
(like type signatures and members) on functions,
structs, and other things within the program.

`--disable-hint-validation`

Disable the hint validation, which ordinarily checks
program hints against a whitelist.

`--account-contract`

Compile as account contract, which means the ABI will
be checked for expected builtin entry points.

`--prime PRIME`

The positive integer size of the finite field. This is
a (usually large) prime power over which basic
arithmetic within the program is carried out.

`--cairo_path CAIRO_PATH`

A list of directories, separated by ":" to resolve
import paths. The full list will consist of
directories defined by this argument, followed by the
environment variable `CAIRO_PATH`, the working directory
and the standard library path.

`--preprocess`

Stop after the preprocessor step and output the
preprocessed program, which consists only of low-level
Cairo (e.g. frame pointer and allocation pointer
manipulations) along with annotations indicating
relevant source code locations.

`--output OUTPUT`

The output file name (default: stdout).

`--no_debug_info`

Don't include debug information in the compiled file.
Removes the 'debug_info' field from the JSON output,
which by default contains an 'instruction_locations'
map with information on flow tracking data, hints,
accessible scopes, and source code location.

`--cairo_dependencies CAIRO_DEPENDENCIES`

Path to dump a list of the Cairo source files used
during the compilation as a CMake file.

`--no_opt_unused_functions`

Disable unused function optimization, which ordinarily
only compiles functions reachable from the main scope
in the dependency graph, i.e. functions that are
actually called.

`-v, --version`

Show program's version number and exit

