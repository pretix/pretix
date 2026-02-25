#!/bin/sh
REPO_DIR=$(git rev-parse --show-toplevel)
GIT_DIR=$REPO_DIR/.git
VENV_ACTIVATE=$VIRTUAL_ENV/bin/activate
if [[ ! -f $VENV_ACTIVATE ]]
then
    echo "Could not find your virtual environment"
fi

echo "#!/bin/sh" >> $GIT_DIR/hooks/pre-commit
echo "set -e" >> $GIT_DIR/hooks/pre-commit
echo "source $VENV_ACTIVATE" >> $GIT_DIR/hooks/pre-commit
echo "black --check ." >> $GIT_DIR/hooks/pre-commit
echo "isort -c ." >> $GIT_DIR/hooks/pre-commit
echo "flake8 ." >> $GIT_DIR/hooks/pre-commit
chmod +x $GIT_DIR/hooks/pre-commit
