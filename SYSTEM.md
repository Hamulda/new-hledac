# SYSTEM (universal scope)

## Scope enforcement
- Allowed root: /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal
- Always `cd` here before any command.
- Use only relative paths under this root.

## Preferred terminal tools
- rg, fd, sg (ast-grep)
- ruff (check + format)
- diff -u (pipe to delta)

## No-git diff protocol (required)
- Before editing: cp file file.bak
- After editing: diff -u file.bak file | delta
- Include evidence in task.progress/task.done
