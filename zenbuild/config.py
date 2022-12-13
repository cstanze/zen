import shutil
import os
import sys
import yaml
from .provider import LANGUAGE_DEFAULTS, COMPILER_DEFAULTS

from zenbuild.verifier import ZenVerifier


class Config:
    """
    Config options

    verbose - Enable verbose output (unimplemented)
    jobs - Number of jobs to run in parallel (unimplemented)
    build_dir - The build directory (unimplemented)
    profile - The profile to use (unimplemented)
    target - The target to build (unimplemented)
    """

    def __init__(self, args):
        # print("Loading config")
        self.verbose = args.verbose
        self.config_dir = args.config_dir
        self.raw_mode = args.raw

        # Get the config from the directory
        with open(os.path.join(self.config_dir, "build.zen"), "r") as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)
            # print(self.config)

        # Validate the config
        verifier = ZenVerifier(self.config)
        try:
            valid, doc = verifier.verify()
        except Exception as e:
            print("Validator error")
            print(f"{e}")

        if not valid:
            # print(doc)
            # print("classification:")
            # print("")
            errs = verifier.classify_errors(doc)
            def print_errs(errs, parent=None):
                for err in errs:
                    # print(err)
                    if "suberr" in err:
                        print_errs(err["suberr"], f"{parent}[{err['field']}]" if parent is not None else err["field"])
                    else:
                        field = f"{parent}[{err['field']}]" if parent is not None else err["field"]
                        print(f"Zen Config - `{field}`: {err['error']}")

            print_errs(errs)
            sys.exit(1)
            # raise Exception()
            #print("Invalid config:")
            #print(f"{doc}")

        self.vcfg = doc
        
        # remove .zencache file if it exists
        # create it again
        self.zencache = os.path.join(self.config_dir, ".zencache")
        with open(self.zencache, "a") as f:
            f.close() # create it just in case

        # then we can read it for the cached dep mtimes
        # the format looks like the following:
        # {file}:{mtime}
        self.cached_deptimes = {}
        with open(self.zencache, "r") as f:
            for line in f.readlines():
                line = line.strip()
                if line != "":
                    file, mtime = line.split(":")
                    self.cached_deptimes[file] = float(mtime)

    # Make it subscriptable
    def __getitem__(self, key):
        return self.vcfg[key]

    def solve_depedency_graph(self):
        """
        returns a tuple:
        (passed_without_error, value if passed_without_error else errorString)
        """
        targets = self["targets"]
        graph = {}

        # first we need to build the graph
        for target in targets:
            if target['name'] in graph:
                graph[target['name']]["dependencies"] = target["dependencies"]
            else:
                graph[target['name']] = {
                    "dependencies": target['dependencies'],
                    "dependents": [],
                }
            for dep in target['dependencies']:
                if dep not in graph:
                    graph[dep] = {
                        "dependencies": [],
                        "dependents": [target['name']],
                    }
                else:
                    graph[dep]['dependents'].append(target['name'])

        # now we need to check for circular dependencies
        # two basic rules:
        # 1. a target cannot depend on itself
        # 2. a target cannot depend on a target that depends on the original target
        # let's do that now:
        for target in graph:
            if target in graph[target]["dependencies"]:
                return False, f"Target `{target}` depends on itself, circular dependency"
            for dep in graph[target]["dependencies"]:
                if target in graph[dep]["dependencies"]:
                    return False, f"Target `{target}` depends on a target that depends on it, circular dependency"

        # now we need to solve the graph
        # and return the order of the targets
        # to build
        # we can use a topological sort
        # https://en.wikipedia.org/wiki/Topological_sorting

        # first we need to find the nodes with no dependencies
        # these are the nodes that we can start with
        # we can then remove them from the graph
        # and repeat the process until the graph is empty
        # they'll be sorted in the order that they can be built
        order = []

        while len(graph) > 0:
            # find the nodes with no dependencies
            no_deps = []
            for node in graph:
                if len(graph[node]["dependencies"]) == 0:
                    no_deps.append(node)
            
            # if there are no nodes with no dependencies
            # then there is a circular dependency
            if len(no_deps) == 0:
                return False, "Circular dependency detected"

            # remove the nodes with no dependencies from the graph
            for node in no_deps:
                for dep in graph[node]["dependents"]:
                    graph[dep]["dependencies"].remove(node)
                del graph[node]
            
            # add the nodes with no dependencies to the order
            order.extend(no_deps)

        result = []
        for target in order:
            # they expect target objects
            # so we need to find the target object
            # that matches the name
            target_found = False
            for t in targets:
                if t['name'] == target:
                    target_found = True
                    result.append(t)
                    break
            
            if not target_found:
                # if we didn't find the target
                # then something went wrong
                # so we should raise an error
                return False, f"Target `{target}` not found but was in the dependency graph"


        return True, result

    def find_compiler(self, lang):
        """
        Find a suitable C/C++ compiler

        First search the PATH for a compiler (in order):
        cc, gcc, clang

        (c++, g++, and clang++ if cpp is True)

        If none found (and CC/CXX is not set) then raise an error

        If CC/CXX is set, then use that compiler
        over the default compiler

        TODO: Support for Windows compilers (cl, cl.exe, etc)
        """

        if lang in self["overrides"]["compiler"]:
            comp = shutil.which(self["overrides"]["compiler"][lang])
            if comp is not None:
                return comp
            raise Exception("No suitable compiler found")

        if lang in LANGUAGE_DEFAULTS:
            if lang == "CC" and "CC" in os.environ and shutil.which(os.environ["CC"]) and not self["overrides"]["ignore_env_compiler"]:
                return shutil.which(os.environ["CC"])
            elif lang == "CXX" and "CXX" in os.environ and shutil.which(os.environ["CXX"]) and not self["overrides"]["ignore_env_compiler"]:
                return shutil.which(os.environ["CXX"])

            if lang in COMPILER_DEFAULTS:
                if shutil.which(COMPILER_DEFAULTS[lang]) is not None:
                    return shutil.which(COMPILER_DEFAULTS[lang])
                else:
                    # Should we allow changing these defaults?
                    # They would mostly apply to non-CC, non-CXX,
                    # etc. languages.
                    raise Exception("No suitable compiler found")

            compiler_list = (
                ["cc", "gcc", "clang"]
                if lang == "CC" else
                ["c++", "g++", "clang++"]
            )

            for compiler in compiler_list:
                if shutil.which(compiler) is not None:
                    return shutil.which(compiler)
 
        raise Exception("No suitable compiler found")

    def get_compiler_config(self, lang):
        if lang in self["overrides"]["languages"]:
            return self["overrides"]["languages"][lang]
        
        if lang in LANGUAGE_DEFAULTS:
            return LANGUAGE_DEFAULTS[lang]
        
        raise Exception("No suitable compiler config found")

    def exists(self, path):
        return os.path.exists(path)
    
    def cache_deptimes(self):
        with open(self.zencache, "w") as f:
            f.write("")
        with open(self.zencache, "a") as f:
            for dep in self.cached_deptimes:
                f.write(f"{dep}:{self.cached_deptimes[dep]}\n")

    def as_object(self, target, file):
        f, ext = os.path.splitext(file)
        return f"build/{target['name']}/{f.replace('.', '_').replace(os.path.sep, '_')}_{ext.replace('.','')}.o"

    def depchanged(self, dep, obj=None, extra=False):
        if not extra:
            if obj is None:
                raise Exception("Expected obj not to be None")
            if not self.exists(obj):
                return True
            if not self.exists(dep):
                return False
            return os.path.getmtime(obj) < os.path.getmtime(dep)
        else:
            if dep in self.cached_deptimes:
                # print(f"from cache: {self.cached_deptimes[dep] < os.path.getmtime(dep)}")
                # print(f"cached: {self.cached_deptimes[dep]}")
                # print(f"current: {os.path.getmtime(dep)}")
                return self.cached_deptimes[dep] < os.path.getmtime(dep)
            # print(f"caching {dep} with time: {os.path.getmtime(dep)}")
            self.cached_deptimes[dep] = os.path.getmtime(dep)
            self.cache_deptimes() # can become a HUGE disk op, any better way?
            return False

