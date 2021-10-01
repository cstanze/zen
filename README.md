# Zen Build

A clean build system for small projects with a level of scalablity!

## Getting started

To get started with Zen build, you can install the `main.py` file as an executable on the path for ease of use. For example, I installed `main.py` in a personal `~/.scripts` folder on my path. I was able to access zen by just using `zen` in the shell.

Next, you have to create a `build.zen` file in some directory. You can fill it with targets and the file format is YAML.

## The `build.zen` Format

### Setup

First, you *must* setup the `build.zen` file with compilers for each language.

```yaml
# Here's an example
setup:
  compilers:
    CC: "clang"
```

`CC` can be anything as long as you keep that same language name throughout the file's targets. You can change the compiler language and binary (path or name) to anything you'd like.

### Targets

Targets is a list of targets with a name, language, sources, etc.

```yaml
# This is an example...
targets:
  # Since Python3.7+ uses ordered dictionaries
  # it's built in order!

  - name: ExampleLib
    language: CC
    type: "library"
    static: true # gives us a nice lil 'libExampleLib.a'
    flags:
      - "-Wall"
      - "-pedantic"
      - "-g"
    sources:
      - "lib.c"
    extra_deps:
      - "lib.h"
  
  - name: ExampleTarget
    language: CC # Remember that language name?
    flags:
      - "-Wall"
      - "-pedantic"
      - "-g"
    link_flags:
      - "-Lbuild/ExampleLib"
      - "-lExampleLib"
    sources:
      - "some/simple/source.c"
      - searchdir: "or_recursive_sources"
        regex: .+\.c
    extra_deps:
      - "not_built/but_tracked/deps.h"
      - searchdir: "same_recursive_structure"
        regex: .+\.h
```

This example shows all available options to a developer creating a `build.zen` file. As noted, you can use the order of the targets to denote the order in which the targets must be built.

In the example, we build `ExampleLib` before `ExampleTarget` because we link against `ExampleLib`!

Also, we can recursively look for `sources` or `extra_deps` by using a dictionary with `searchdir` and `regex` as a list item. Zen will look through the directory (and all subdirectories) for files that match the regex! This makes adding sources easier than ever.

Finally, since we can change the language name and compiler, the options for Zen are endless!

## Using `zen`

Using `zen` itself is easy enough! You can use `zen build` to build the targets in `build.zen` (as long as its in the current directory).  It'll automatically create a directory named `build` to store build artifacts.

`zen clean` will clear out the `build` directory without deleting it.

Some options you can use are:

- `-v` For verbose output
- `-j <jobs>` To set the number of ***targets*** building in parallel.

Please note: `-j` only applies to ***targets*** and not individual sources. In the future, this behavior may change.

Other than those 2 commands and 2 options, you've learned how to use Zen! Hope you enjoy and Happy Coding!
