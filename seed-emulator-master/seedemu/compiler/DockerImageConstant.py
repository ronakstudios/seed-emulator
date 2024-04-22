from .DockerImage import DockerImage
from seedemu.core import BaseSystem

UBUNTU_IMAGE   = DockerImage(name='ubuntu:20.04',
                                software=[],
                                subset=None)

BASE_IMAGE     = DockerImage(name='handsonsecurity/seedemu-base',
                                software=['zsh', 'curl', 'nano', 'vim-nox', 'mtr-tiny', 'iproute2',
                                        'iputils-ping', 'tcpdump', 'termshark', 'dnsutils', 'jq', 'ipcalc', 'netcat'],
                                subset=UBUNTU_IMAGE)

ROUTER_IMAGE   = DockerImage(name='handsonsecurity/seedemu-router',
                                software=['bird2'],
                                subset=BASE_IMAGE)

ETHEREUM_IMAGE = DockerImage(name='handsonsecurity/seedemu-ethereum',
                                software=['software-properties-common', 'python3', 'python3-pip'],
                                subset=BASE_IMAGE)

UBUNTU_IMAGE_RONAK   = DockerImage(name='ubuntu:latest',
                                software=[],
                                subset=None)                     

BASE_IMAGE_RONAK     = DockerImage(name='ronakparikhnj/seedemu-base-latestubuntu',
                                software=['zsh', 'curl', 'nano', 'vim-nox', 'mtr-tiny', 'iproute2',
                                        'iputils-ping', 'tcpdump', 'termshark', 'dnsutils', 'jq', 'ipcalc', 'netcat'],
                                subset=UBUNTU_IMAGE_RONAK)
                                
ETHEREUM_IMAGE_RONAK = DockerImage(name='ronakparikhnj/seedemu-ethereum-usingsigp',
                                software=['software-properties-common', 'python3', 'python3-pip'],
                                subset=BASE_IMAGE_RONAK)     
                                
ROUTER_IMAGE_RONAK   = DockerImage(name='ronakparikhnj/seedemu-router-latestubuntu',
                                software=['bird2'],
                                subset=BASE_IMAGE_RONAK)
                                
ETHEREUM_IMAGE_RONAK2 = DockerImage(name='ronakparikhnj/seedemu-ethereum-custom32',
                                software=['software-properties-common', 'python3', 'python3-pip'],
                                subset=BASE_IMAGE)                             

BASESYSTEM_DOCKERIMAGE_MAPPING = {
        BaseSystem.UBUNTU_20_04:     UBUNTU_IMAGE,#_RONAK,
        BaseSystem.SEEDEMU_BASE:     BASE_IMAGE,#_RONAK,
        BaseSystem.SEEDEMU_ROUTER:   ROUTER_IMAGE,#_RONAK,
        BaseSystem.SEEDEMU_ETHEREUM: ETHEREUM_IMAGE_RONAK2
    }
