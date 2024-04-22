PoS Ethereum Emulator
---

### Installation
Install the following dependencies:
* python3
* pip
* web3
* networkx
* strip_ansi
* dsplot (need to also install graphviz and libgraphviz-dev)
* pyvis
* matplotlib
* docker
* docker-compose, specifically version 2.20.2 (avaliable [here](https://github.com/docker/compose/releases/tag/v2.20.2))

Depending on which way you installed docker compose (standalone or part of docker) you may need to change the last line of the setup program (blockchain-pos.py) from `docker compose` to `docker-compose` (2 occurrences in the line). If you are running on a hpc may need to comment out the line and do it manually (see later)

Start by changing directory to the seed emulator folder and running `source development.env`

Change directory to the ETH Emulator program, modify the clients and topology for your application then run `python3 blockchain-pos.py`. The last line of `blockchain-pos.py` is supposed to open a new terminal and use docker-compose to build and run the emulation. If it is not working you can do it manually by changing directory to the generated folder `output` and running
`sudo docker compose build` and `sudo docker compose up` (or `docker-compose`). You can then manage the running emulation with the controller: `python3 Controller.py`

When you first run `sudo docker compose build` it may fail because it is missing some required docker images. To fix this, navigate to `output/dummies` and look at the contents of those files. It should say something like "FROM handsonsecurity/seedemu-router". Remove the "FROM " and use docker pull on the rest of the string like so:
`docker pull handsonsecurity/seedemu-router`
After doing this, docker compose build may still keep giving the same error. As far as I am aware this is a glitch or a cache not clearing and the solution is unfortunately to repeatedly run docker compose build for about 10 minutes until it realizes it has the dependency.
