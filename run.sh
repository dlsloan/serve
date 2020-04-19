#!/bin/bash
trap 'printf "\0----------ENV----------\n\0" 1>&2; env -0 1>&2' exit;
"$@"