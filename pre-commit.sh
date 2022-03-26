#!/bin/bash

# install via ln -s ../../pre-commit.sh .git/hooks/pre-commit

tmp=$(mktemp)
git diff > $tmp
git apply --allow-empty -R $tmp

$HOME/.local/bin/poe pre-commit
code=$?

git add -u
git apply --allow-empty $tmp
rm $tmp

exit $code
