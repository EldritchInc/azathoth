#!/bin/sh

find ./azathoth ./tests -name '*.*' -print0 | xargs -0 -I{} sh -c 'echo {}; echo "==================================" ; echo; echo ; cat {} ; echo' | pbcopy
