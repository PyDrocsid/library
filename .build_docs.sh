#!/bin/bash

repo=$(mktemp -d)
git clone --recursive https://github.com/PyDrocsid/documentation.git $repo
rm -rf $repo/library
mkdir $repo/library
cp -r * $repo/library/
pushd $repo

./pages_build.sh

popd
mv $repo/site .
rm -rf $repo
