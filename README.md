# Zen Build

A clean build system for small projects with a level of scalablity!

## Getting started

To get started with Zen build, you can install using `python setup.py install`. This'll make `zen` available on your PATH and `zenbuild` will be an available module on your system.
Next, you have to create a `build.zen` file in some directory. From there, you can build up your targets and enjoy the ease of Zen Build.

## The `build.zen` Format

### Setup

First, you must setup the `build.zen` file with `zen init`.
You can take this basic file layout and add targets

### Targets

Targets is a list of targets with a name, language, sources, etc.

```yaml

global:
  flags:
    - "-Wall"
    - "-pedantic"
    - "-g"

targets:
  - name: ExampleLib
    language: CC
    type: "library"
    static: true
    flags:
      - inherit # inherits global flags
    prebuild:
      - clang-format -style=file lib.c lib.h # format the 
    sources:
      - "lib.c"
    watching:
      - "lib.h"
  
  - name: ExampleTarget
    # not required, but if these entries were out of order,
    # it would be reordered before building
    depends_on: ExampleLib
    language: CC
    flags:
      - inherit
      - "-std=c99" # use c99 here but not in ExampleLib
    link_flags:
      - kind: lib
        target: ExampleLib
    sources:
      - "some/simple/source.c"
      - path: "or_recursive_sources"
        regex: .+\.c
    watching:
      - "not_built/but_tracked/deps.h"
      - path: "same_recursive_structure"
        regex: .+\.h
```

This example shows only a few available options to a developer creating a `build.zen` file.

In the example, we build `ExampleLib` before `ExampleTarget` because we link against `ExampleLib`.
Also, we can recursively look for `sources` or `watching` by using a dictionary with `path` and `regex` as a list item. Zen will look through the directory (and all subdirectories) for files that match the regex. This makes adding sources far easier than many other build systems.

## Using `zen`

Using `zen` itself is easy enough! You can use `zen` to build the targets in `build.zen` (as long as its in the current directory or if the config directory if defined by options).  It'll automatically create a directory named `build` to store build artifacts.

`zen clean` will clear out the `build` directory and delete it.

Some options you can use are:

- `-r` or `--raw` for raw output of commands used in building or `-r`/`--recursive` during `zen init` to recursively init (or reinit) the `build.zen` file.  
- `-c` or `--config-dir` to set the config directory (mostly used if the config is not in the current directory)

