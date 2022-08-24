# [NESTrisOCR](https://github.com/alex-ong/NESTrisOCR) to [NESTrisChamps](https://github.com/timotheeg/nestrischamps) Connector

This receives frame data from NESTrisOCR and forwards it to one or more NESTrisChamps servers via a websocket.  Currently translates the data into a Version 1 [Binary Frame](https://github.com/timotheeg/nestrischamps/blob/main/public/js/BinaryFrame.js).    

Can also save the received frames to a file.  The frames can be played back to a NESTrisChamps server at a later time.

## Setup

Works in Python 3.10 on windows.  Recommend installing in a virtual environment.  When installed, there's an entrypoint `ntcpycon`.

Set up a configuration yaml file and run `ntcpycon config.yml`.

Without installing, can be run as a module:  `python -m ntcpycon` 


## Exiting

Ctrl+C will cause the script to exit, but it takes 10-15 seconds for the connections to close before this happens.  Sending another Ctrl+C will cause it to exit immediately but will throw RuntimeError('Event loop is closed').  There's room for improvement.  


## Example Starting Config

If you have an account on [NESTrisChamps](https://nestrischamps.herokuapp.com) get your secret from [here](https://nestrischamps.herokuapp.com/settings).  Save the following as a `.yml` or `.yaml` file, whichever you prefer.

```
receiver:
  tcp_server:
    port: 3338

senders:
  websockets:
    - uri: wss://nestrischamps.herokuapp.com/ws/room/producer/<secret>

```


## Credit

Thanks to [NESTrisChamps](https://github.com/timotheeg/nestrischamps) and [NESTrisOCR](https://github.com/alex-ong/NESTrisOCR) for these awesome projects.  Also thanks to [nestrischamps-emulator-connector](https://github.com/Stabyourself/nestrischamps-emulator-connector) for showing a path to making this happen.