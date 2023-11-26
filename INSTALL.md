## Clone repository & Update

    git clone https://github.com/zohassadar/ntcpycon
    cd ntcpycon
    git submodule update --init

## Create virtual environment

venv substituted with virtualenv if you have it

    python -m venv .venv
    . .venv/bin/activate
    pip install -e .

If this will only be used with NESTrisOCR, stop here.  If you plan on using this in conjunction with the Everdrive & TetrisGYM, proceed.

## Install python-edlinkn8

Make sure .venv environment is active

    git submodule update --remote
    cd python-edlinkn8
    pip install -r requirements.txt
    pip install -e .

## Create GYM Rom & Patch

This requires placing the file `Tetris (U) [!].nes` (you may have your rom backed up with a different filename) with an md5sum of `ec58574d96bee8c8927884ae6e7a2508` in the folder TetrisGYM with the name `clean.nes`.

    git submodule update --remote
    docker run --rm -u $(id -u):$(id -g) -v $PWD/TetrisGYM:/code zohassadar/nesdev bash ed2ntc.sh

This builds the files ed2ntc.ips and ed2ntc.nes in TetrisGYM/
