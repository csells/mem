unalias find 2>/dev/null || true
unalias grep 2>/dev/null || true
find() {
  command -v bfs >/dev/null 2>&1 || { command find "$@"; return; }
  command bfs -S dfs -regextype findutils-default "$@"
}
grep() {
  local _zcode_grep_arg
  for _zcode_grep_arg in "$@"; do
    case "$_zcode_grep_arg" in -*-filter*|-*-pager*|-*-view*|-*-format-open*|-*-config*|---*|-@*|-*-save-config*|-[Zz]*|-[!-]*[Zz]*|--null|--null-data) command grep "$@"; return ;; esac
  done
  command -v ugrep >/dev/null 2>&1 || { command grep "$@"; return; }
  command ugrep -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-dir=.bzr --exclude-dir=.jj --exclude-dir=.sl "$@"
}