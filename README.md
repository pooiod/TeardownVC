# TeardownVC (super wip)
A simple voice chat system for Teardown.

## Getting started
download the latest release from [here](https://github.com/pooiod/TeardownVC/releases)
install the teardown mod from here [here](https://steamcommunity.com/sharedfiles/filedetails/?id=3653434619)

## Features
- Proximity voice chat

## Planned features to add
- Cave echoing
- Global voice chat

## How it works
The Teardown mod saves your player position into `%LocalAppData%\Teardown\savegame.xml` then the TDVP executable will read your save data and sync voices across clients

## Building your own
The TDVP client is made in python
you can use something like [autopytoexe](https://pypi.org/project/auto-py-to-exe) to compile it <br>
You will need to publish the mod to the woekshop to use it in multiplayer, then you set the `SAVE_TAG` var to the resulting steam id in your savegame.xml
