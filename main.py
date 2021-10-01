#!/usr/bin/env python3

# Tabs are 2 spaces, no hard tabs
# Use LF line endings (unix)
# Use UTF-8 encoding
# Python 3, pyyaml

import yaml
import argparse
import os
import re
import sys
import subprocess
import asyncio
from typing import List, Union, Tuple


class ZenCommandRunner:
  def __init__(self):
    self.targets = []
    self.compilers = {}
    self.cached_deptimes = {}

    # load .zencache
    if os.path.isfile(".zencache"):
      with open(".zencache", "r") as f:
        for line in f:
          (path, mtime) = line.split(":")
          self.cached_deptimes[path] = float(mtime)

  def find_files(self, directory: str, regex: str):
    files = []
    for root, dirs, filenames in os.walk(directory):
      for filename in filenames:
        if re.match(regex + "$", filename):  # auto append $
          files.append(os.path.join(root, filename))
    return files

  def is_file(self, path: str):
    return os.path.isfile(path)

  def is_dir(self, path: str):
    return os.path.isdir(path)

  def exists(self, path: str):
    return os.path.exists(path)

  def depchanged(self, obj: str, orig: str) -> bool:
    if not self.exists(obj):
      return True
    if not self.exists(orig):
      return False  # don't know if this is possible
    return os.path.getmtime(obj) < os.path.getmtime(orig)

  def extra_depchanged(self, orig: str) -> bool:
    if not self.exists(orig):
      return False
    if orig in self.cached_deptimes:
      return self.cached_deptimes[orig] < os.path.getmtime(orig)
    self.cached_deptimes[orig] = os.path.getmtime(orig)
    # TODO: this rewrites the whole file every time, is there a better way?
    self.cache_deps()
    return False

  def cache_deps(self):
    # open .zencache and clear it
    with open(".zencache", "w") as f:
      f.write("")
    for dep in self.cached_deptimes:
      with open(".zencache", "a") as f:
        f.write(f"{dep}:{self.cached_deptimes[dep]}\n")

  def target_deps_built(self):
    if len(self.targets) == 0:
      return True

    for target in self.targets:
      build_dir = f"build/{target['name']}"
      for source in target['sources']:
        if self.depchanged(f"{build_dir}/{'_'.join(filter(lambda x: x != '.', source.split('/')))}.o", source):
          return False
      for dep in target['extra_deps']:
        if self.extra_depchanged(dep):
          return False
    return True

  # type, static, link_flags
  def add_target(
    self,
    style: str,
    name: str,
    se: Tuple[List[str], List[str]],
    language: str,
    flags: List[str],
    post_build_commands: List[str],
    ty: str,
    static: bool,
    link_flags: List[str],
  ):
    self.targets.append({
        'style': style,
        'name': name,
        'language': language,
        'flags': flags,
        "post_build_commands": post_build_commands,
        'sources': se[0],
        'extra_deps': se[1],
        'type': ty,
        'static': static,
        'link_flags': link_flags,
    })

  def add_compiler(self, name: str, binary: str):
    self.compilers[name] = binary

  async def run(self, opts: dict):
    """
    {
      "verbose": bool,
      "jobs": int,
    }
    """
    # Run all the targets in parallel
    while len(self.targets) > 0:
      for i in range(opts["jobs"]):
        if len(self.targets) == 0:
          break
        await self.build_next_target(opts)
      if opts["verbose"]:
        print(f"{len(self.targets)} targets remaining")

  async def build_next_target(self, opts: dict):
    target = self.targets.pop()

    # Create build directory
    build_dir = f"build/{target['name']}"
    if not os.path.exists(build_dir):
      os.makedirs(build_dir)
    else:
      subprocess.run(["rm", "-rf", build_dir])
      os.makedirs(build_dir)

    args = [self.compilers[target['language']], *target['flags']]

    i = 0
    for source in target['sources']:
      split_src = list(filter(lambda x: x != ".", source.split('/')))

      if self.exists(f"{build_dir}/{'_'.join(split_src)}.o"):
        if self.depchanged(f"{build_dir}/{'_'.join(split_src)}.o", source):
          subprocess.run(["rm", "-rf", f"{build_dir}/{'_'.join(split_src)}.o"])
        else:
          continue

      if target['style'] is None:
        # <clear line> [<current source index>/<total source count>] Building <source>...
        print(f"[{i}/{len(target['sources'])}] Building {source}...")
      else:
        if target['style'] == "ninja":
          # <clear line> [<current source index>/<total source count>] Building <source>...
          print(f"[{i}/{len(target['sources'])}] Building {source}...")
        elif target['style'] == "redis":
          # \t<compiler name>\t<source>
          print(f"{' ' * 4}{target['language']}{' ' * 4}{source}")

      proc = subprocess.run([*args, "-c", "-o", f"{build_dir}/{'_'.join(split_src)}.o",
                             source], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

      # If return code is not 0, raise with stderr
      if proc.returncode != 0:
        print("\n")
        print(proc.stderr.decode())
        sys.exit(1)

      i += 1

    outfile = (
      f"{build_dir}/{target['name']}"
      if target['type'] == "executable" else
      f"{build_dir}/{target['name']}.{self.library_ext(target['static'])}"
    )
    proc = subprocess.run(
        [
            *args, "-o", outfile,
            *target['link_flags'],
            *[
                f"{build_dir}/" +
                "_".join(filter(lambda x: x != ".", source.split('/'))) + ".o"
                for source in target['sources']
            ]
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )

    # If return code is not 0, raise with stderr
    if proc.returncode != 0:
      print("\n")
      print(proc.stderr.decode())
      sys.exit(1)

    for command in target["post_build_commands"]:
      
      command = command.replace('{outfile}', outfile)
      command = command.replace('{build_dir}', build_dir)
      command = command.replace('{target_name}', target['name'])
      command = command.replace('{target_language}', target['language'])

      proc = subprocess.run(command, shell=True, stdout=subprocess.DEVNULL)
      if proc.returncode != 0:
        print("\n")
        print(proc.stderr.decode())
        sys.exit(1)

  def library_ext(self, static: bool):
    if static:
      return "a"
    else:
      # macOS doesn't support .so, so we use .dylib if we're on macOS
      if sys.platform == "darwin":
        return "dylib"
      else:
        return "so"

class ZenBuildParser:
  def __init__(self, runner: ZenCommandRunner):
    self.config = {}
    self.runner = runner
    with open("build.zen", "r") as f:
      self.config = yaml.load(f, Loader=yaml.FullLoader)

  def parse(self):
    if not isinstance(self.config, dict):
      print("Invalid build.zen file")
      return

    if "setup" in self.config:
      setup = self.config["setup"]

      if isinstance(setup, dict):
        if "compilers" in setup:
          compilers = setup["compilers"]
          if isinstance(compilers, dict):
            for name, compiler in compilers.items():
              if not isinstance(compiler, str):
                print("Invalid compiler in setup")
                return
              if not isinstance(name, str):
                print("Invalid compiler name in setup")
                return
              self.runner.add_compiler(name, compiler)
          else:
            print("Invalid compiler setup info in build.zen")
            return
      else:
        print("Invalid setup info in build.zen")
        return

    if "targets" not in self.config:
      print("No targets found in build.zen")
      return

    targets = self.config["targets"]
    if not isinstance(targets, list):
      print("Invalid targets in build.zen")
      return

    for target in targets:
      if not isinstance(target, dict):
        print("Invalid target in build.zen")
        return
      self.parse_target(target)

  def parse_target(self, target: dict):
    if "name" not in target:
      print("No name found in target in build.zen")
      return

    if "language" not in target:
      print("No language found in target in build.zen")
      return

    if "flags" not in target:
      print("No flags found in target in build.zen")
      return

    name = target["name"]
    language = target["language"]
    flags = target["flags"]

    if "post_build" not in target:
      post_build = []
    else:
      post_build = target["post_build"]
      if not isinstance(post_build, list):
        print("Invalid post_build in target in build.zen")
        return

    if "sources" not in target:
      print("No sources found in target in build.zen")
      return

    pre_sources = target["sources"]

    if not isinstance(pre_sources, list):
      print("Invalid sources in target in build.zen")
      return

    sources = []
    for source in pre_sources:
      sources.extend(self.parse_recursable(source))

    if "extra_deps" in target:
      _extra_deps = target["extra_deps"]

    extra_deps = []

    for dep in _extra_deps:
      extra_deps.extend(self.parse_recursable(dep))

    if "style" not in target:
      style = None
    else:
      style = target["style"]

    if "type" not in target:
      type = "executable"
    else:
      if target["type"] == "executable":
        type = "executable"
      elif target["type"] == "library":
        type = "library"
      else:
        print("Invalid type in target in build.zen")
        return
    
    if type == "library" and "static" not in target:
      static = True
    else:
      static = target["static"]
      if not isinstance(static, bool):
        print("Invalid static in target in build.zen")
        return
    
    if "link_flags" not in target:
      link_flags = []
    else:
      link_flags = target["link_flags"]
      if not isinstance(link_flags, list):
        print("Invalid link_flags in target in build.zen")
        return

    if not isinstance(style, str) and style is not None:
      print("Invalid style in target in build.zen")
      return

    if not isinstance(sources, list):
      print("Invalid sources in target in build.zen")
      return

    if not isinstance(flags, list):
      print("Invalid flags in target in build.zen")
      return

    if not isinstance(language, str):
      print("Invalid language in target in build.zen")
      return

    if not isinstance(name, str):
      print("Invalid name in target in build.zen")
      return

    # Add target to runner
    self.runner.add_target(
        style, name, (sources, extra_deps), language, flags, post_build, type, static, link_flags)

  def parse_recursable(self, recurseable: Union[str, dict]):
    if isinstance(recurseable, str):
      return [recurseable]
    elif isinstance(recurseable, dict):
      if "searchdir" not in recurseable:
        print("No searchdir found in recurseable in build.zen")
        return

      searchdir = recurseable["searchdir"]

      if "regex" not in recurseable:
        print("No regex found in recurseable in build.zen")
        return

      regex = recurseable["regex"]

      # Recursively search for files
      files = self.runner.find_files(searchdir, regex)

      # Add files to sources
      return files
    else:
      print("Invalid recurseable in build.zen")
      return

shared_opts = {
  "verbose": False,
  "jobs": 1,
}

async def main():
  # Parse args
  parser = argparse.ArgumentParser(
    description="Zen Build System (Beta)",
    epilog="Copyright (c) 2021, Constanze"
  )

  parser.add_argument("-j", "--jobs", type=int, default=1, help="Number of jobs to run simultaneously")
  parser.add_argument("-v", "--verbose", type=bool, default=False, help="Verbose output")

  # Add subcommands (no need to use the returned parsers for these)
  subparsers = parser.add_subparsers(dest="command")
  _ = subparsers.add_parser("build", help="Build a target")
  _ = subparsers.add_parser("clean", help="Clean a target")

  args = parser.parse_args()

  # If no command is specified, exit
  if args.command is None:
    parser.print_help()
    sys.exit(1)

  # If clean is specified, clean the target
  if args.command == "clean":
    # Remove build directory
    if os.path.exists("build"):
      subprocess.run(["rm", "-rf", "build"])
    
    # Create build directory again
    os.makedirs("build")

    # Exit
    sys.exit(0)

  if args.command != "build":
    parser.print_help()
    sys.exit(1)

  shared_opts["verbose"] = args.verbose
  shared_opts["jobs"] = args.jobs

  # Check for cwd/.zen file
  if ".zen" in os.listdir("."):
    # Load .zen file
    with open(".zen", "r") as f:
      # Config format:
      #   <option> -> <value> (number, string, bool, list of numbers, list of strings, list of bools)
      #   ...

      # Parse options
      for line in f:
        line = line.strip()
        if line == "":
          continue
        if line[0] == "#":
          continue
        if "->" in line:
          option, value = line.split("->")
          option = option.strip()
          value = value.strip()
          if value == "True":
            value = True
          elif value == "False":
            value = False
          elif value.isdigit():
            value = int(value)
          elif value[0] == "[" and value[-1] == "]":
            values = value[1:-1].split(",")
            for i in range(len(values)):
              if values[i].isdigit():
                value = int(values[i])
              elif values[i] == "True":
                value = True
              elif values[i] == "False":
                value = False
              else:
                value = values[i]
          shared_opts[option] = value
        else:
          print("Invalid line in .zen file: " + line)
          return

  config = ZenBuildParser(ZenCommandRunner())
  config.parse()

  if config.runner.target_deps_built():
    print("No changed targets to build")
    return

  await config.runner.run(shared_opts)
  

if __name__ == "__main__":
  shared_opts["async_loop"] = asyncio.get_event_loop()
  shared_opts["async_loop"].run_until_complete(main())

  # Clean up
  shared_opts["async_loop"].close()
