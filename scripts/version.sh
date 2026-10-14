# Sourced by the build scripts (from the repo root): sets $ver, same rule everywhere. Release tag = v$ver.
ver=$(git describe --tags --always --dirty)
ver=${ver#v}
git describe --tags >/dev/null 2>&1 || ver=0.0.0+g$ver   # no tags: bare hash
[[ $ver =~ ^[0-9]+(\.[0-9]+)*- ]] && ver=${ver/-/+}  # tag-N-gHASH -> tag+N-gHASH
ver=$(printf '%s' "$ver" | tr -c 'A-Za-z0-9.+~:\n-' '.')
