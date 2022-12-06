from .provider import LANGUAGE_DEFAULTS
from cerberus import Validator
import pprint
import json


class VerificationError(Exception):
    pass


PROJECT_SCHEMA = {
    "name": {"type": "string"},
    "version": {"type": "string"},
    "languages": {
        "type": "list",
        "schema": {"type": "string"}
    }
}


LANGUAGE_SUBSCHEMA = {
    "type": "dict",
    "schema": {
        "name": {"type": "string", "required": True},
        "define_pattern": {"type": "string"},
        "include_pattern": {"type": "string"},
        "link_pattern": {
            "type": "dict",
            "schema": {
                "file": {"type": "string"},
                "dir": {"type": "string"}
            }
        },
        "standard": {"type": "string"},
        "std_pattern": {"type": "string"},
        "extensions": {
            "type": "dict",
            "schema": {
                "source": {
                    "type": "list",
                    "schema": {"type": "string"},
                    "required": True
                },
                "header": {
                    "type": "list",
                    "schema": {"type": "string"},
                    "required": True
                }
            }
        }
    }
}

OVERRIDE_SCHEMA = {
    "compiler": {
        "type": "dict"
    },
    "languages": {
        "type": "list",
        "schema": LANGUAGE_SUBSCHEMA
    },
    "ignore_env_compiler": { "type": "boolean", "default": False }
}

_DEFINE_VALUE_SUBSCHEMA_BASE = {
    "symbol": {"type": "string", "required": True}
}

DEFINE_VALUE_SUBSCHEMAS = [
    {
        **_DEFINE_VALUE_SUBSCHEMA_BASE,
        "value": {"type": ["string", "number", "boolean"], "required": True},
        "as_type": {"type": "string", "allowed": ["int", "string", "bool"]}
    },
    {
        **_DEFINE_VALUE_SUBSCHEMA_BASE,
        "command": {"type": "string", "required": True},
        "strip_whitespace": {"type": "boolean", "default": False},
        "ignore_fail": {"type": "boolean", "default": True},
        "use_stderr": {"type": "string", "allowed": ["yes", "fail", "no"], "default": "no"}
    }
]

DEFINE_SUBSCHEMA = {
    "type": "dict",
    "oneof_schema": DEFINE_VALUE_SUBSCHEMAS
}

FLAG_SUBSCHEMA = {
    "type": "list",
    "schema": {
        "type": ["string", "dict"],
        "schema": {
            "kind": { "type": "string", "required": True, "allowed": ["include_dir"] },
            "value": { "type": "string", "required": True }
        }
    }
}

GLOBAL_SCHEMA = {
    "flags": FLAG_SUBSCHEMA,
    "defines": {
        "type": "list",
        "schema": DEFINE_SUBSCHEMA
    }
}

LINK_FLAG_SUBSCHEMA = {
    "type": ["dict", "string"],
    "schema": {
        "kind": {"type": "string", "required": True, "allowed": ["lib"]},
        "target": {"type": "string", "required": True},
    }
}

SOURCE_SUBSCHEMA = {
    "type": ["string", "dict"],
    "schema": {
        "path": {"type": "string"},
        "regex": {"type": "string"}
    }
}

TARGET_SUBSCHEMA = {
    "type": "dict",
    "schema": {
        "name": {"type": "string", "required": True},
        "language": {"type": "string", "required": True},
        "dependencies": { "type": "list", "schema": {"type": "string"}, "default": [] },
        # Not having `sources` or `watching`
        # required allows for some flexibility
        "sources": {
            "type": "list",
            "schema": SOURCE_SUBSCHEMA,
            "default": []
        },
        "watching": {
            "type": "list",
            "schema": SOURCE_SUBSCHEMA,
            "default": []
        },
        "flags": FLAG_SUBSCHEMA,
        "link_flags": {
            "type": "list",
            "schema": LINK_FLAG_SUBSCHEMA
        },
        "type": {"type": "string", "allowed": ["library", "executable"], "default": "executable"},
        "static": {"type": "boolean", "default": False},
        "defines": {
            "type": "list",
            "schema": DEFINE_SUBSCHEMA
        },
        "prebuild": {
            "type": "list",
            "schema": {"type": "string"},
            "default": []
        },
        "postbuild": {
            "type": "list",
            "schema": {"type": "string"},
            "default": []
        }
    }
}

PROJECT_INFO_SCHEMA = {
    "name": {
        "type": "string",
        "required": True
    },
    "version": {
        "type": "string",
        "required": True
    },
    "languages": {
        "type": "list",
        "required": True,
        "schema": {
            "type": "string"
        }
    }
}

PROJECT_SCHEMA = {
    "project": {
        "type": "dict",
        "required": True,
        "schema": PROJECT_INFO_SCHEMA
    },
    "overrides": {
        "type": "dict",
        "schema": OVERRIDE_SCHEMA,
        "default": {
            "compiler": {},
            "languages": [],
            "ignore_env_compiler": False
        }
    },
    "global": {
        "type": "dict",
        "schema": GLOBAL_SCHEMA
    },
    "targets": {
        "type": "list",
        "schema": TARGET_SUBSCHEMA,
        "required": True
    }
}


class ZenValidator(Validator):
    pass


class ZenErrors:
    @staticmethod
    def classify_err_string(s):
        if s == "required field":
            return "Required Field"
        elif s == "unknown field":
            return "Unknown Field"
        elif "must be of" in s:
            return f"Expected '{s[11:-5]}' type"
        elif "unallowed value " in s:
            return f"Value `{s[16:]}` not allowed"
        else:
            # raise Exception(f"Unknown Err String: {s}")
            return f"Unknown err string: {s}"


class ZenVerifier:
    def __init__(self, config):
        self.config = config

    def verify(self):
        if not isinstance(self.config, dict):
            raise VerificationError("Config is not a dictionary")

        project_validator = ZenValidator(PROJECT_SCHEMA)
        # print(json.dumps(self.config, indent=2))

        valid = project_validator.validate(self.config)
        if not valid:
            return False, project_validator.errors

        return True, project_validator.document

    def classify_errors(self, errors, parent=None):
        classified = []
        for key in errors:
            val = errors[key]
            # it is always a list from what I've seen
            for err in val:
                if isinstance(err, str):
                    classified.append({
                        "error": ZenErrors.classify_err_string(err),
                        "field": (
                            f"{parent}[{key}]"
                            if parent
                            else key
                        )
                    })
                elif isinstance(err, dict):
                    if parent:
                        classified.append({
                            "field": parent,
                            "suberr": self.classify_errors(err)
                        })
                    else:
                        for subkey in err:
                            # print(err)
                            # print(subkey)
                            suberr = err[subkey]
                            # print(suberr)
                            # usually a list
                            for subsuberr in suberr:
                                if isinstance(subsuberr, str):
                                    classified.append({
                                        "error": ZenErrors.classify_err_string(subsuberr),
                                        "field": f"{subkey}" # makes formatting easier later
                                    })
                                elif isinstance(subsuberr, dict):
                                    classified.extend(self.classify_errors(subsuberr, f"{key}[{subkey}]"))

                        #classified.extend(self.classify_errors(err, list(err.keys())[0]))
        # print(errors)
        # print("--- classified as ---")
        # print(classified)
        # print("")
        return classified
