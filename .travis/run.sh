#!/bin/bash

function run_flake8() {
    pip install flake8
    flake8 --ignore=W503,E203
}

if [[ $SYSTEM_TEST == "true" ]]; then
    ./.travis/system_test.sh
    exit $?
fi

if [[ $TRAVIS_OS_NAME == 'osx' ]]; then
    eval "$(pyenv init -)"
    pyenv global 3.6.10
fi

coverage run --branch --source _repobee,repobee_plug,repobee_testhelpers -m pytest tests/unit_tests tests/new_integration_tests
test_status=$?
coverage report
exit $test_status
