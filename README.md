# TeardownVC (WIP)
TeardownVC is a simple proximity voice chat system for Teardown.

## Getting started
1. Download the TDVC client [github.com/pooiod/TeardownVC/releases](https://github.com/pooiod/TeardownVC/releases)
2. Install the Teardown mod [steamcommunity.com/sharedfiles/filedetails/?id=3653434619](https://steamcommunity.com/sharedfiles/filedetails/?id=3653434619)

## Features
- Proximity voice chat
- Global voice chat
- Automatic mute on player death

## Planned features
- Cave echoing
- Multiple audio sources (ex: walkie-talkies)
- More audio effects

## How it works
The Teardown mod writes the player’s position to `%LocalAppData%\Teardown\savegame.xml` <br>
The TeardownVC client reads this data to find out where to play audio from.

## Building your own
The TeardownVC client is written in Python. <br>
You can compile it using tools like: [auto-py-to-exe](https://pypi.org/project/auto-py-to-exe/) <br>
To use the mod in multiplayer, you must publish it to the Steam Workshop. 
After publishing, set the `SAVE_TAG` value to the to the mod’s Steam Workshop ID. (ex: `steam-3653434619`)
