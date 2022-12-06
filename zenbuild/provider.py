C_FAMILY_DEFAULTS = {
    "define_pattern": "-D{}={*}",
    "include_pattern": "-I{}",
    "link_pattern": "-l{}",
    "link_dir_pattern": "-L{}",
    "default_link_flags": [
        "-lobjc"
    ],
    "default_compile_flags": [],
}

COMPILER_DEFAULTS = {}

LANGUAGE_DEFAULTS = {
    "CC": {
        "extensions": {
            "source": [".c"],
            "header": [".h"]
        },
        **C_FAMILY_DEFAULTS
    },
    "CXX": {
        "extensions": {
            "source": [".cpp", ".cc", ".cxx"],
            "header": [".hpp", ".hh", ".hxx"],
        },
        **C_FAMILY_DEFAULTS
    },
    "OBJC": {
        "extensions": [".m", ".h"],
        **C_FAMILY_DEFAULTS
    },
    "OBJCXX": {
        "extensions": {
            "source": [".mm"],
            "header": [".hh", ".hpp"]
        },
        **C_FAMILY_DEFAULTS
    }
}
