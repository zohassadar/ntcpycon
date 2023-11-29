# [NESTrisChamps](https://github.com/timotheeg/nestrischamps) Connector

Connector for NESTrisChamps that can receive game data from the following sources:

* [NESTrisOCR](https://github.com/alex-ong/NESTrisOCR)
* directly from Everdrive (Coming soon!)

## NESTrisOCR

This receives frame data from NESTrisOCR and forwards it to one or more NESTrisChamps servers via a websocket.  Currently translates the data into a Version 3 [Binary Frame](https://github.com/timotheeg/nestrischamps/blob/main/public/js/BinaryFrame.js).    

Can also save the received frames to a file.  The frames can be played back to a NESTrisChamps server at a later time.

## Everdrive

*Coming Soon!*

This uses a modified version of [TetrisGYM](https://github.com/zohassadar/TetrisGYM/tree/ed2ntc) and a USB connection to an [Everdrive Pro](https://krikzz.com/our-products/cartridges/everdrive-n8-pro-72pin.html) to get game data directly.

## Setup

See [**INSTALL.md**](INSTALL.md) for installation steps

Set up a configuration yaml file and run `ntcpycon <filename>.yml`.

Without installing, can be run as a module:  `python -m ntcpycon` 


## Exiting

Ctrl+C will cause the script to exit, but it takes 10-15 seconds for the connections to close before this happens.  Sending another Ctrl+C will cause it to exit immediately but will throw RuntimeError('Event loop is closed').  There's room for improvement.  


## Example Starting Config

If you have an account on [NESTrisChamps](https://nestrischamps.io) get your secret from [here](https://nestrischamps.io/settings).  Save the following as a `.yml` or `.yaml` file, whichever you prefer.

```
receiver:
  ocr_server:
    port: 3338

senders:
  websockets:
    - uri: wss://nestrischamps.io/ws/room/producer/<secret>

```


## Credit

Thanks to [NESTrisChamps](https://github.com/timotheeg/nestrischamps) for such an awesome project.  Thanks for [this post](https://github.com/timotheeg/nestrischamps/issues/107) showing that I'm not the only one that wanted this feature and also for the very helpful hints on how to make it happen.  Thanks to [NESTrisOCR](https://github.com/alex-ong/NESTrisOCR) for the great source of information.  Also thanks to [nestrischamps-emulator-connector](https://github.com/Stabyourself/nestrischamps-emulator-connector) for being a guide on how to make this happen.
