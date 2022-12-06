from cerberus.platform import sys
from .provider import LANGUAGE_DEFAULTS
from .config import Config
import os
import re
import pprint
import subprocess

def libext():
    # TODO: include support for Windows devices
    if os.uname().sysname == "Darwin":
        return ".dylib"
    else:
        return ".so"

def zprint(config, *args, **kwargs):
    raw_only = False if "raw" not in kwargs else kwargs["raw"]
    if config.raw_mode and not raw_only:
        return

    end = None if "end" not in kwargs else kwargs["end"]
    print(*args, end=end)

def flatten_files(sect):
    """
    sect is the `sources` or `watching`
    section in config
    """
    files = []
    for file in sect:
        if isinstance(file, str):
            files.append(file)
        elif isinstance(file, dict):
            for root, _, path_files in os.walk(file["path"]):
                for found in path_files:
                    if re.match(file["regex"], found):
                        files.append((root + os.path.sep + found))
    return files

def flatten_flags(config, target):
    """
    sect is the flags list (compile or link, all the same)
    throws an array of errors if any exist
    otherwise returns tuple of two arrays (in this order):
        an array of all flattened compile flags
        an array of all flattened link flags
    """
    flags = []
    link_flags = []
    errs = []
    did_inherit = False
    compiler_config = config.get_compiler_config(target["language"])
    if "flags" in target:
        for flag in target["flags"]:
            if flag == "inherit":
                if did_inherit:
                    errs.append(f"Already inherited flags in target: {target['name']}")
                    continue
                did_inherit = True
                flags.extend(config["global"]["flags"])
            elif isinstance(flag, dict):
                if flag["kind"] == "include_dir":
                    flags.append(compiler_config["include_pattern"].replace("{}", flag["value"]))
            else:
                flags.append(flag)

    if "link_flags" in target:
        for flag in target["link_flags"]:
            if isinstance(flag, dict):
                if not len(list(filter(lambda x: x["name"] == flag["target"], config["targets"]))) > 0:
                    errs.append(f"Unknown target to link ({flag['target']}) to target: {target['name']}")
                    continue
                link_flags.extend([
                    compiler_config["link_dir_pattern"].replace("{}", f"build/{flag['target']}/"),
                    compiler_config["link_pattern"].replace("{}", f"{flag['target']}")
                ])
            else:
                link_flags.append(flag)

    if "defines" in target:
        for define in target["defines"]:
            symbol = define["symbol"]
            if "value" in define:
                value = define["value"]
                if "as_type" in define:
                    if define["as_type"] == "int":
                        try:
                            value = int(define["value"])
                        except:
                            errs.append(f"Failed to cast define symbol ({symbol}) value to `int`")
                            continue
                    elif define["as_type"] == "string":
                        value = str(define["value"])
                    elif define["as_type"] == "bool":
                        value = bool(define["value"])
                flags.append(
                    compiler_config["define_pattern"]
                        .replace("{}", symbol)
                        .replace("{*}", value)
                )
            elif "command" in define:
                res = subprocess.run(define["command"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode != 0 and not define["ignore_fail"]:
                    errs.append(f"Failed to run command for define rule ({symbol})")
                    continue
                value = ""
                if define["use_stderr"] == "fail" and res.returncode != 0 or define["use_stderr"] == "yes":
                    value = res.stderr.decode()
                else:
                    value = res.stdout.decode()
                flags.append(
                    compiler_config["define_pattern"]
                        .replace("{}", symbol)
                        .replace("{*}", value.strip() if define["strip_whitespace"] else value)
                )
            else:
                errs.append("Unknown define rule")
                continue

    if len(errs) > 0:
        return (False, errs)

    return (True, (flags, link_flags))

def artifacts(config):
    """
    This is called after the sanity of the config is
    verified and calculates the required build artifacts
    that are to be created (both by zen and by the compilation process)
    
    Note: artifacts created by Zen and compilation are separate items in
    a tuple as to allow `config_sanity` to create Zen's requirements

    The data structure for the return value may look like the following:
    (
        [(some_zen_artifact, if artifact is dir, True, else, False)],
        [some_compiler_artifact, another_compiler_artifact]
    )
    """
    target_names = [target["name"] for target in config["targets"]]  

    cc_files = []
    for target in config["targets"]:
        sources = flatten_files(target["sources"])
        for source in sources:
            file, ext = os.path.splitext(source)
            cc_files.append(f"{file.replace('.', '_')}_{ext.replace('.', '')}.o")

    build_dirs = lambda path: [(path.replace("target_name", target_name), True) for target_name in target_names]
    sep = os.path.sep

    return (
        [
            *build_dirs(f"build{sep}target_name{sep}"),
            # *build_dirs(f"bin{sep}target_name{sep}"),
            (".zencache", False)
        ],
        [
            cc_files
        ]
    )


def config_sanity(config, skip_creation=False):
    """
    At this point, the config should've been verified
    but here we'll need to verify the config once more.
    
    This isn't a redo of the previous pass but instead
    a series of checks for verify the validity of the config.
    
    This includes checking if files exist, if targets exist,
    and creating directories for build artifacts (unless
    skip_creation is set)
    """
    errs = []
    for target in config["targets"]:
        sources = flatten_files(target["sources"])
        watching = flatten_files(target["watching"])
        passed, res = flatten_flags(config, target)
        zen_artifacts, _ = artifacts(config)

        # print(f"files: {files}")
        # print(f"zen_artifacts: {zen_artifacts}")

        # verify flags
        if not passed:
            errs.extend(res)

        # verify that all files exist
        for file in sources:
            if not os.path.exists(file):
                errs.append(f"File doesn't exist but is in the Zen config: {file}")

        for file in watching:
            if not os.path.exists(file):
                errs.append(f"File doesn't exist but is in the Zen config: {file}")

        # create basic artifacts if needed
        if not skip_creation:
            for artifact, is_dir in zen_artifacts:
                if is_dir:
                    try:
                        os.makedirs(artifact)
                    except:
                        # likely already created
                        continue
                else:
                    try:
                        open(artifact, "x")
                    except:
                        # likely already created
                        continue

        # check if all the languages we declared in project
        # are defined in `override` (whether languages or compiler)
        for language in config["project"]["languages"]:
            not_in_compilers = language not in config["overrides"]["compiler"]
            not_in_langs = len(list(filter(lambda x: x["name"] == language, config["overrides"]["languages"]))) == 0
            not_predefined = language not in LANGUAGE_DEFAULTS


            if not_in_compilers and not_in_langs and not_predefined:
                errs.append(f"Unknown language ({language}) is not defined in `overrides[compiler]` or `overrides[languages]`")

            if not_in_compilers and not not_in_langs and not_predefined:
                # it's config is defined but no compiler bin path
                errs.append(f"Language without compiler binary path provided ({language}) in `overrides[compiler]`")
        
    if len(errs) > 0:
        return errs

    return True


def build(config):
    if not isinstance(config, Config):
        raise TypeError("config must be an instance of Config")
   
    res = config_sanity(config)
    if res != True:
        print("Invalid config:")
        for err in res:
            print(f"  {err}")
        return

    passed, res = config.solve_depedency_graph()
    if not passed:
        print("Invalid config:")
        print(f"  {res}")

    # pprint.pprint(res)
    # return

    for target in res:
        sources = flatten_files(target["sources"])
        watching = flatten_files(target["watching"])
        _, res = flatten_flags(config, target)
        flags, link_flags = res

        # lets get building!
        # print(sources)
        # print(watching)
        # print(flags)

        compiler = config.find_compiler(target["language"])
        # print(compiler)

        any_dep_changed = False
        for dep in sources:
            obj = config.as_object(target, dep)
            if config.depchanged(dep, obj):
                any_dep_changed = True

        for dep in watching:
            # print("watching", dep)
            if config.depchanged(dep, extra=True):
                # print("matched")
                any_dep_changed = True

        
        config_changed = config.depchanged(os.path.join(config.config_dir, "build.zen"), extra=True)
        if not (any_dep_changed or config_changed):
            zprint(config, f"[0/0] No changes in {target['name']}")
            continue

        i = 1
        task_count = len(target["prebuild"]) + len(sources) + len(target["postbuild"])

        # run prebuild 
        for cmd in target["prebuild"]:
            zprint(config, f"\r[{i}/{task_count}] Running prebuild for {target['name']}...", end="")
            res = subprocess.call(
                cmd
                    .replace("{build_dir}", f"build/{target['name']}/")
                    .replace("{target_name}", target["name"]),
                shell=True,
            )

            if res != 0:
                print()
                break

            i += 1
        if len(target["prebuild"]) > 0:
            zprint(config)
        

        # go through each source and build each object
        objects = []
        last_len = 0
        for source in sources:
            file, ext = os.path.splitext(source) 
            object = f"build/{target['name']}/{file.replace('.', '_').replace(os.path.sep, '_')}_{ext.replace('.', '')}.o"
            objects.append(object)

            zprint(config, f"{' ' * last_len}", end="")
            last_len = len(f"[{i}/{task_count}] Building {file}{ext}")
            zprint(
                config,
                f"\r[{i}/{task_count}] Building {file}{ext}",
                end=""
            )
            
            proc = subprocess.run([
                compiler,
                "-c",
                *flags,
                "-o",
                object,
                source
            ], stderr=subprocess.PIPE)

            zprint(
                config,
                f"{compiler} -c {' '.join(flags)} -o {object} {source}",
                raw=True
            )

            if proc.returncode != 0:
                print()
                print(proc.stderr.decode())
                sys.exit(1)

            i += 1
        zprint(config, f"\r[{i}/{task_count}] Linking target {target['name']}")

        proc = None
        outfile = (f"build/{target['name']}/{target['name']}"
                        if target['type'] == "executable"
                        else
                        f"build/{target['name']}/lib{target['name']}{'.a' if target['static'] else libext()}")
        if target["type"] == "executable":
            proc = subprocess.run([
                compiler,
                *flags,
                *link_flags,
                "-o",
                outfile,
                *objects
            ], stderr=subprocess.PIPE)
            zprint(
                config,
                f"{compiler} {' '.join(flags)} {' '.join(link_flags)} -o {outfile} {' '.join(objects)}",
                raw=True
            )
        elif target["type"] == "library":
            if target["static"]:
                proc = subprocess.run([
                    "ar", "rcs",
                    outfile,
                    *objects
                ], stderr=subprocess.PIPE)
                zprint(
                    config,
                    f"ar rcs {outfile} {' '.join(objects)}",
                    raw=True
                )
            else:
                proc = subprocess.run([
                    compiler,
                    *flags,
                    *link_flags,
                    "-shared",
                    "-o",
                    outfile,
                    *objects,
                ], stderr=subprocess.PIPE)
                zprint(
                    config,
                    f"{compiler} {' '.join(flags)} {' '.join(link_flags)} -shared -o {outfile} {' '.join(objects)}",
                    raw=True
                )

        if proc.returncode != 0:
            print()
            print(proc.stderr.decode())
            sys.exit(1)

        # run postbuild 
        for cmd in target["postbuild"]:
            zprint(config, f"\r[{i}/{task_count}] Running postbuild on {target['name']}...", end="")
            res = subprocess.call(
                cmd
                    .replace("{build_dir}", f"build/{target['name']}/")
                    .replace("{target_name}", target["name"])
                    .replace("{outfile}", outfile),
                shell=True
            )
            
            if res != 0:
                break
            
            i += 1
        if len(target["postbuild"]) > 0:
            zprint(config)

    
    config.cache_deptimes()


def clean(config):
    if not isinstance(config, Config):
        raise TypeError("config must be an instance of Config")

    res = config_sanity(config, skip_creation=True)
    if res != True:
        print("Invalid config:")
        for err in res:
            print(f"  {err}")
        return

    # all compiler artifacts should be stored in zen directories
    zen, _ = artifacts(config)
  
    remove = lambda p: subprocess.run([ "rm", "-rf", p ])

    for artifact, _ in zen:
        try:
            remove(artifact)
        except:
            # again, likely it was already deleted
            continue 

    try:
        remove('./build/')
    except:
        pass

    pass
